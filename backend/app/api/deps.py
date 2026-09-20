"""Dependency wiring for the HTTP layer.

FastAPI builds these per request, and a test can replace any one of them with
`app.dependency_overrides`. That is what lets the API tests run against the fake
provider and an in-memory database without a single patch.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from functools import lru_cache
from typing import Annotated

import secrets

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings
from app.db.session import create_db_engine, create_session_factory
from app.db.types import configure_cipher
from app.email.base import EmailSender
from app.email.registry import build_email_sender
from app.providers.base import FlightDataProvider
from app.providers.cache import wrap_with_cache
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
    factory: Annotated[sessionmaker[Session], Depends(get_session_factory)],
) -> FlightDataProvider:
    """Built once per configuration and reused.

    The fake loads its scenario file on construction and the real adapter holds
    connection settings; rebuilding either on every request is waste.

    The cache wraps each source SEPARATELY, inside the chain rather than around
    it. Two reasons. A cached miss on the paid feed still lets the free one be
    asked, which is the whole point of having a chain. And the stored rows are
    keyed by which source said so -- which is what lets the nightly archive,
    written by the board under its own name, answer a question months later
    through the same table.
    """
    inner = _provider(settings.flight_provider, settings.aerodatabox_api_key)
    if not settings.flight_cache:
        return inner
    return wrap_with_cache(
        inner, factory, ttl=timedelta(minutes=settings.flight_cache_ttl_minutes)
    )


@lru_cache
def _email_sender(name: str, fingerprint: str) -> EmailSender:
    return build_email_sender(name, get_settings())


def get_email_sender(
    settings: Annotated[Settings, Depends(get_settings_dependency)],
) -> EmailSender:
    """Built once per configuration and reused.

    The fingerprint is in the cache key so a changed host or sender produces a
    new adapter rather than silently reusing one pointed at the old server.
    """
    return _email_sender(
        settings.email_sender, f"{settings.smtp_host}|{settings.email_from}"
    )


@lru_cache
def _storage(root: str) -> FileStorage:
    return LocalFileStorage(Path(root))


def get_file_storage(
    settings: Annotated[Settings, Depends(get_settings_dependency)],
) -> FileStorage:
    """Built once per configured root. Creating the directory on every upload
    would be pointless work on the hot path of the slowest request we serve."""
    return _storage(str(settings.upload_dir))


def require_admin(
    settings: Annotated[Settings, Depends(get_settings_dependency)],
    x_admin_key: Annotated[str | None, Header()] = None,
) -> None:
    """Guard every admin endpoint.

    Three behaviours worth naming:

    * No key configured means the admin API is CLOSED, and says so with 503.
      Failing open would ship an unprotected list of every customer's name,
      email and national identity number because somebody forgot a variable.
    * The comparison is constant-time. A normal string comparison returns as
      soon as it finds a difference, and the timing of that leaks the key one
      character at a time to anybody patient enough to measure it.
    * A wrong key and a missing key get the identical response, so probing
      cannot distinguish "there is no admin API here" from "you guessed wrong".

    This is a shared secret, which is the right amount of security for an
    internal tool with a handful of operators and the wrong amount for anything
    with real user accounts. Replacing it means changing this function.
    """
    if not settings.admin_api_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The admin API is not configured on this deployment.",
        )
    if x_admin_key is None or not secrets.compare_digest(
        x_admin_key, settings.admin_api_key
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing admin key.",
            headers={"WWW-Authenticate": "X-Admin-Key"},
        )


def build_engine_and_factory(settings: Settings) -> tuple[Engine, sessionmaker[Session]]:
    # The encryption key is handed over here because this is the one function
    # every entry point already calls -- the API's lifespan, the archive job,
    # the enrichment job. Anywhere a session can be opened, the key is in place
    # before the first query; there is no path to the database that misses it.
    configure_cipher(settings.encryption_keys)
    engine = create_db_engine(settings.database_url)
    return engine, create_session_factory(engine)
