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
        def _enforce_foreign_keys(connection, _record) -> None:  # type: ignore[no-untyped-def]
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


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
