"""Tests for the Alembic migrations.

The question these answer is not "does Alembic work" -- it does -- but "does
running the migrations produce the schema the code expects?"

That gap is the classic way a migration setup fails: somebody adds a column to
the models, the tests pass because tests build the schema with create_all(),
and the next deploy runs migrations that never heard of the column. The
comparison test below closes it.
"""

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from app.db.models import Base
from app.db.session import create_all, create_db_engine

BACKEND = Path(__file__).resolve().parents[2]


def alembic_config(database_url: str) -> Config:
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


@pytest.fixture
def database_url(tmp_path: Path) -> str:
    """SQLite by default; a real PostgreSQL when TEST_DATABASE_URL points at one.

    This is the file where the difference matters. SQLite does not enforce
    declared column widths, has no native uuid or timestamptz, and accepts
    schema changes PostgreSQL refuses -- so a migration that passes here on
    SQLite can still fail on the database this is deployed to. Running the same
    tests against both is the only way to know before deploying.

        docker compose up -d
        TEST_DATABASE_URL=postgresql+psycopg://flight:flight@localhost:5433/flight_system \
          uv run pytest tests/integration/test_migrations.py

    The schema is dropped and recreated per test, because a migration test that
    inherits the last one's tables is testing nothing.
    """
    configured = os.environ.get("TEST_DATABASE_URL", "").strip()
    if not configured:
        return f"sqlite:///{tmp_path / 'migrated.db'}"

    engine = create_engine(configured)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    engine.dispose()
    return configured


# --- The migrations run ------------------------------------------------------


def test_upgrade_creates_the_schema(database_url: str) -> None:
    command.upgrade(alembic_config(database_url), "head")

    tables = inspect(create_engine(database_url)).get_table_names()
    assert "eligibility_checks" in tables
    assert "alembic_version" in tables  # how the database remembers where it is


def test_downgrade_removes_it_again(database_url: str) -> None:
    """A migration that cannot be undone is a migration nobody dares deploy on
    a Friday."""
    config = alembic_config(database_url)
    command.upgrade(config, "head")
    command.downgrade(config, "base")

    assert "eligibility_checks" not in inspect(
        create_engine(database_url)
    ).get_table_names()


def test_upgrade_is_repeatable(database_url: str) -> None:
    """Running it twice must be a no-op, because deploy scripts get re-run."""
    config = alembic_config(database_url)
    command.upgrade(config, "head")
    command.upgrade(config, "head")

    assert "eligibility_checks" in inspect(
        create_engine(database_url)
    ).get_table_names()


# --- The migrations match the models -----------------------------------------


def _schema(engine, schema: str | None = None) -> dict[str, object]:  # type: ignore[no-untyped-def]
    inspector = inspect(engine)
    return {
        table: {
            "columns": {
                column["name"]: (
                    str(column["type"]).upper(),
                    bool(column["nullable"]),
                )
                for column in inspector.get_columns(table, schema=schema)
            },
            "indexes": {
                index["name"]: tuple(index["column_names"])
                for index in inspector.get_indexes(table, schema=schema)
            },
            "primary_key": tuple(
                inspector.get_pk_constraint(table, schema=schema)["constrained_columns"]
            ),
        }
        for table in sorted(inspector.get_table_names(schema=schema))
        if table != "alembic_version"
    }


def test_the_migrated_schema_matches_the_models(
    database_url: str, tmp_path: Path
) -> None:
    """The single most important test in this file.

    Tests build their schema with create_all(), straight from the models, so a
    column added to a model is instantly visible to every test. Production
    builds its schema from migrations. Nothing connects the two, so the day
    somebody adds a column and forgets the migration, every test still passes
    and the deploy breaks.

    This compares the two schemas column by column and index by index. If they
    ever diverge, it fails here rather than on a server.
    """
    command.upgrade(alembic_config(database_url), "head")
    migrated = _schema(create_engine(database_url))

    # Both schemas must be built on the SAME dialect, or this compares
    # PostgreSQL's UUID against SQLite's CHAR(32) and fails on a difference
    # that is not a difference. On PostgreSQL the models go into a second
    # schema in the same database; on SQLite, a second file.
    if database_url.startswith("sqlite"):
        engine = create_db_engine(f"sqlite:///{tmp_path / 'from_models.db'}")
        create_all(engine)
        from_models = _schema(engine)
    else:
        # A second DATABASE rather than a second schema: `metadata.schema` is
        # read when a Table is defined, so setting it afterwards silently does
        # nothing and the comparison quietly passes against an empty schema.
        engine = create_engine(_sibling_database(database_url))
        create_all(engine)
        from_models = _schema(engine)
        engine.dispose()

    assert migrated == from_models


def _sibling_database(url: str) -> str:
    """An empty database beside the one under test, on the same server."""
    from sqlalchemy.engine import make_url

    parsed = make_url(url)
    name = f"{parsed.database}_from_models"
    # render_as_string(hide_password=False), not str(): URL.__str__ masks the
    # password, so the rendered URL authenticates as nobody.
    admin = create_engine(
        parsed.set(database="postgres").render_as_string(hide_password=False),
        isolation_level="AUTOCOMMIT",
    )
    with admin.connect() as connection:
        connection.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    admin.dispose()
    return parsed.set(database=name).render_as_string(hide_password=False)


def test_every_model_index_survives_the_migration(database_url: str) -> None:
    """Indexes are the easiest thing to lose in a hand-edited migration, and
    their absence shows up as slowness rather than as an error."""
    command.upgrade(alembic_config(database_url), "head")

    indexes = {
        index["name"]
        for index in inspect(create_engine(database_url)).get_indexes(
            "eligibility_checks"
        )
    }
    assert "ix_checks_review_queue" in indexes  # the operator's morning query
    assert "ix_checks_flight" in indexes  # everyone on one flight


# --- The migration history ---------------------------------------------------


def test_there_is_exactly_one_head(database_url: str) -> None:
    """Two heads means two people wrote a migration from the same parent.

    Alembic then refuses to upgrade, and the fix is a merge revision written
    under deploy pressure. Better to fail in CI.
    """
    script = ScriptDirectory.from_config(alembic_config(database_url))
    assert len(script.get_heads()) == 1


def test_the_models_are_fully_migrated(database_url: str) -> None:
    """Autogenerate against an up-to-date database must find nothing left to do.

    This is what catches a model change that has no migration -- from the other
    direction than the schema comparison above, and with a much clearer message
    when it fails.
    """
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    command.upgrade(alembic_config(database_url), "head")

    engine = create_engine(database_url)
    with engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={"compare_type": True})
        differences = compare_metadata(context, Base.metadata)

    assert differences == [], (
        "The models and the migrations have diverged. Run:\n"
        "  DATABASE_URL=sqlite:////tmp/x.db uv run alembic revision --autogenerate -m '...'"
    )


def test_batch_mode_is_enabled_for_sqlite() -> None:
    """SQLite has no ALTER COLUMN at all.

    Batch mode makes Alembic emit the only thing that works there -- create a
    new table, copy the rows, drop, rename. Without it the first migration that
    changes a column type fails, and the fix has to be hand-written under
    pressure.
    """
    env = (BACKEND / "migrations" / "env.py").read_text()
    assert env.count("render_as_batch=True") == 2  # online and offline modes


def test_the_database_url_is_not_committed() -> None:
    """A URL in a config file is a URL that eventually points at production
    from somebody's laptop."""
    ini = (BACKEND / "alembic.ini").read_text()
    assert "\nsqlalchemy.url = " not in ini


def test_running_migrations_does_not_silence_the_application(
    database_url: str,
) -> None:
    """fileConfig must not disable loggers it did not configure.

    Python's logging.config.fileConfig defaults disable_existing_loggers to
    True, which turns OFF every logger not named in the file it just read. Run
    `alembic upgrade head` in-process at startup with that default and the
    application never logs again, with nothing to explain it.

    This surfaced as two email tests that passed alone and failed in the full
    suite: a migration test had run first and switched their logger off.
    """
    import logging

    command.upgrade(alembic_config(database_url), "head")

    # Asserted on the logger itself rather than through caplog: fileConfig also
    # replaces the ROOT logger's handlers, including the one pytest installs to
    # capture with, so an empty caplog after a migration says nothing about
    # whether the application can log. `disabled` is the flag that actually
    # changed, and the one the bug set.
    for name in ("flight_system", "flight_system.email"):
        assert logging.getLogger(name).disabled is False, name
