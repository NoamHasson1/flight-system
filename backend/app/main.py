"""The FastAPI application.

An app *factory* rather than a module-level `app = FastAPI()`, so tests can
build an application with different settings instead of monkey-patching a global
one into the right shape.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.deps import build_engine_and_factory
from app.api.routes import (
    admin,
    claims,
    disruptions,
    eligibility,
    health,
    regulations,
)
from app.config import Settings, get_settings

logger = logging.getLogger("flight_system")


def _configure_logging(settings: Settings) -> None:
    """Apply LOG_LEVEL to the application's own logger.

    Set on `flight_system` rather than on the root, and with propagate off,
    so the level is ours and stays ours. Anything else that configures logging
    in this process -- Alembic's fileConfig, uvicorn, a test harness -- can then
    change the root logger without silently deciding whether the application's
    own messages appear.

    `settings.log_level` existed for several steps before anything read it,
    which meant the level was whatever the last library to touch logging had
    chosen.
    """
    app_logger = logging.getLogger("flight_system")
    app_logger.setLevel(settings.log_level.upper())

    # The flow trace is its own logger, so it can be silenced without silencing
    # anything else -- and so its lines print bare, without the level and name
    # prefix that would wreck the column alignment.
    flow_logger = logging.getLogger("flight_system.flow")
    flow_logger.setLevel(
        logging.INFO if settings.flow_logging_enabled else logging.WARNING
    )
    flow_logger.propagate = False
    if not flow_logger.handlers:
        bare = logging.StreamHandler()
        bare.setFormatter(logging.Formatter("%(message)s"))
        flow_logger.addHandler(bare)

    if not app_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(levelname)s %(name)s: %(message)s")
        )
        app_logger.addHandler(handler)
    app_logger.propagate = False

DESCRIPTION = """
Checks whether an air passenger is owed compensation for a delayed or cancelled
flight under **EC261** (EU), **UK261** and the **Israeli Aviation Services Law**,
then collects everything needed to file the claim.

Every check returns the reasoning for all three regulations, not just a verdict.
A result of `NEEDS_REVIEW` means exactly that -- it is never a polite "no".

This is an automated estimate, not legal advice.
"""


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    _configure_logging(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # One engine and one session factory for the process, built here and
        # kept on app.state. Building them per request would open a fresh
        # connection pool every time, which is the easiest way to exhaust a
        # database.
        engine, session_factory = build_engine_and_factory(settings)
        app.state.settings = settings
        app.state.engine = engine
        app.state.session_factory = session_factory

        logger.info("starting %s", settings.describe())
        if settings.provider_needs_a_key and not settings.aerodatabox_api_key:
            # A warning, not a crash. The system still works -- every lookup
            # becomes NEEDS_REVIEW rather than a wrong answer -- but somebody
            # needs to know, because that is not what working software looks
            # like from the outside.
            logger.warning(
                "flight_provider=%s but no API key is configured; every lookup "
                "will fail and be reported as NEEDS_REVIEW",
                settings.flight_provider,
            )
        try:
            yield
        finally:
            engine.dispose()
            logger.info("stopped")

    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        description=DESCRIPTION,
        lifespan=lifespan,
        # Hidden in production: the interactive docs are a gift to a developer
        # and a map to anybody else.
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None if settings.is_production else "/redoc",
        openapi_url=None if settings.is_production else "/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(eligibility.router)
    app.include_router(claims.router)
    app.include_router(disruptions.router)
    app.include_router(regulations.router)
    app.include_router(admin.router)
    return app


app = create_app()
