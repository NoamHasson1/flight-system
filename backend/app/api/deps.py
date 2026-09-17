"""Dependency wiring for the HTTP layer.

FastAPI builds these per request, and a test can replace any one of them with
`app.dependency_overrides`. That is what lets the API tests run against the fake
provider and an in-memory database without a single patch.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings
from app.db.session import create_db_engine, create_session_factory
from app.providers.base import FlightDataProvider
from app.storage.files import FileStorage, LocalFileStorage
from app.providers.registry import build_provider


def get_settings_dependency(request: Request) -> Settings:
    """The settings this application was actually built with.

    Read from app.state, which lifespan populates from whatever was passed to
    create_app -- NOT from the global get_settings(), which reads .env.

    The difference matters and was a real bug: routes depending on the global
    ignored the settings their own application was created with, so an
    application built with a temporary upload directory happily wrote files to
    the one in .env. Only the engine behaved, because lifespan sets that from
    the passed settings directly, which is exactly why it went unnoticed.

    The fallback covers an app constructed without lifespan having run.
    """
    return getattr(request.app.state, "settings", None) or get_settings()


def get_engine(request: Request) -> Engine:
    """The engine built once at startup and kept on the app.

    Per-request engines would open a new connection pool for every request,
    which is the single easiest way to exhaust a database.
    """
    return request.app.state.engine


def get_session_factory(request: Request) -> sessionmaker[Session]:
    return request.app.state.session_factory


def get_session(
    factory: Annotated[sessionmaker[Session], Depends(get_session_factory)],
) -> Iterator[Session]:
    """One transaction per request, committed on success.

    A handler that raises leaves nothing half-written; a half-written check is
    worse than no check, because it looks like a real answer.
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


@lru_cache
def _provider(name: str, api_key: str) -> FlightDataProvider:
    return build_provider(name, api_key=api_key)


def get_flight_provider(
    settings: Annotated[Settings, Depends(get_settings_dependency)],
) -> FlightDataProvider:
    """Built once per configuration and reused.

    The fake loads its scenario file on construction and the real adapter holds
    connection settings; rebuilding either on every request is waste.
    """
    return _provider(settings.flight_provider, settings.aerodatabox_api_key)


@lru_cache
def _storage(root: str) -> FileStorage:
    return LocalFileStorage(Path(root))


def get_file_storage(
    settings: Annotated[Settings, Depends(get_settings_dependency)],
) -> FileStorage:
    """Built once per configured root. Creating the directory on every upload
    would be pointless work on the hot path of the slowest request we serve."""
    return _storage(str(settings.upload_dir))


def build_engine_and_factory(settings: Settings) -> tuple[Engine, sessionmaker[Session]]:
    engine = create_db_engine(settings.database_url)
    return engine, create_session_factory(engine)
