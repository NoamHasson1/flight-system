"""Engine and session factory.

SQLite for now. Everything above this file goes through a `Session`, so moving
to PostgreSQL is this URL and nothing else.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base
from app.observability import flow

DEFAULT_DATABASE_URL = "sqlite:///./flight_system.db"


def create_db_engine(url: str = DEFAULT_DATABASE_URL, *, echo: bool = False) -> Engine:
    """Build an engine with SQLite's defaults corrected.

    SQLite ships with foreign keys switched off for backwards compatibility,
    which silently turns every relationship into a suggestion. The claims tables
    in step 15 depend on them, so they are switched on for every connection.
    """
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, echo=echo, future=True, connect_args=connect_args)

    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(connection, _record) -> None:  # type: ignore[no-untyped-def]
            cursor = connection.cursor()

            # Foreign keys ship OFF in SQLite for backwards compatibility, which
            # silently turns every relationship into a suggestion.
            cursor.execute("PRAGMA foreign_keys=ON")

            # Write-ahead logging. In the default rollback-journal mode a single
            # reader blocks every writer, so opening the database in a GUI while
            # the API is running makes every insert fail with "database is
            # locked". WAL lets readers and one writer coexist, which is exactly
            # the shape of local development.
            cursor.execute("PRAGMA journal_mode=WAL")

            # And when a writer genuinely does have to wait, wait rather than
            # failing instantly. Five seconds is far longer than any write here
            # takes and far shorter than a person's patience.
            cursor.execute("PRAGMA busy_timeout=5000")

            cursor.close()

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    _log_writes(factory)
    return factory


# Columns never worth printing, per table. `national_id` is absent rather than
# masked: a masked secret in a log is still a secret in a log, and this is the
# most sensitive field in the system.
_SECRET: dict[str, set[str]] = {
    "passengers": {"national_id"},
}

# Columns that are large and say nothing at a glance.
_NOISY = {"flight_snapshot", "result_detail", "provider_payload", "stored_path"}


def _log_writes(factory: sessionmaker[Session]) -> None:
    """Log every insert and update, from the ORM rather than from call sites.

    A listener rather than a line in each repository function: this way nothing
    can write to the database without appearing, including code written later
    by somebody who never read this file. That is the difference between "the
    writes I remembered to log" and "the writes".
    """

    @event.listens_for(factory, "after_flush")
    def _after_flush(session: Session, _context) -> None:  # type: ignore[no-untyped-def]
        if not flow.enabled():
            return
        for instance in session.new:
            flow.line("db INSERT", _describe(instance))
        for instance in session.dirty:
            if session.is_modified(instance):
                flow.line("db UPDATE", _describe(instance))


def _describe(instance: object) -> str:
    """One readable line for a row, with secrets left out."""
    table = getattr(instance, "__tablename__", type(instance).__name__)
    hidden = _SECRET.get(table, set())

    parts: list[str] = []
    for column in instance.__table__.columns:  # type: ignore[attr-defined]
        name = column.name
        if name in hidden or name in _NOISY:
            continue
        value = getattr(instance, name, None)
        if value is None or value == "":
            continue
        if name.endswith("email"):
            value = flow.mask_email(str(value))
        elif name == "id" or name.endswith("_id"):
            value = f"{str(value)[:8]}…"
        elif isinstance(value, str) and len(value) > 34:
            value = value[:31] + "…"
        parts.append(f"{name}={value}")

    redacted = (hidden | _NOISY) & {c.name for c in instance.__table__.columns}  # type: ignore[attr-defined]
    suffix = f"  (+{len(redacted)} not shown)" if redacted else ""
    return f"{table}  " + "  ".join(parts[:7]) + suffix


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    """A transaction that commits on success and rolls back on failure.

    Written once, here, so no caller has to remember it. A half-written check is
    worse than no check: it looks like a real answer.
    """
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def create_all(engine: Engine) -> None:
    """Create the schema directly, without migrations.

    For tests and for a first local run. Alembic owns the real schema from step
    14 onward; this stays because a test that needs a database should not need a
    migration history too.
    """
    Base.metadata.create_all(engine)


def sqlite_file_url(path: Path) -> str:
    return f"sqlite:///{path}"
