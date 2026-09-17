"""Alembic environment.

Two things here are not boilerplate and are worth reading.

1. The database URL comes from the environment, not from alembic.ini. A URL
   committed to a config file is a URL that eventually points at production
   from somebody's laptop.

2. `render_as_batch` is on. SQLite cannot ALTER a column -- it has no
   `ALTER TABLE ... ALTER COLUMN` at all. Batch mode makes Alembic emit the
   only thing that works there: create a new table, copy the rows, drop the
   old one, rename. Without it, the first migration that changes a column type
   fails on SQLite and the fix has to be hand-written.
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.models import Base  # noqa: E402
from app.db.session import DEFAULT_DATABASE_URL  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Every table Alembic should know about. Importing Base is what makes
# `alembic revision --autogenerate` able to see the models at all.
target_metadata = Base.metadata


def database_url() -> str:
    """Where to migrate, in order of precedence.

    A URL set directly on the Config wins, because setting it there is always
    an explicit act -- the test suite does it to point at a throwaway file, and
    without this the tests would silently migrate the real database instead.
    Otherwise the environment, and only then the default.
    """
    return (
        config.get_main_option("sqlalchemy.url")
        or os.environ.get("DATABASE_URL")
        or DEFAULT_DATABASE_URL
    )


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of running it.

    `alembic upgrade head --sql` produces a script a DBA can read and apply by
    hand, which is how a change reaches a production database nobody lets a
    deploy job connect to directly.
    """
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = database_url()  # noqa: E501

    connectable = engine_from_config(
        configuration, prefix="sqlalchemy.", poolclass=pool.NullPool
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
            # Without this, a column changing from VARCHAR(20) to VARCHAR(40)
            # is invisible to autogenerate and silently never migrated.
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
