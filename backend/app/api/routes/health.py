"""Health endpoints.

Two of them, because they answer different questions and a deployment platform
needs both:

    /health   Am I alive?    -- no dependencies, never fails while the process
                                runs. A restart would not help, so this must not
                                report a downstream outage.
    /health/ready  Can I do my job? -- checks the database and the provider
                                configuration. Failing here takes the instance
                                out of the load balancer without killing it.

Conflating the two is the classic mistake: a liveness probe that checks the
database restarts every instance the moment the database hiccups, turning a
brief outage into a restart storm.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel
from sqlalchemy import Engine, text

from app.api.deps import get_engine, get_settings_dependency
from app.config import Settings
from app.db.types import SecretsUnavailable, _cipher

router = APIRouter(tags=["health"])


class Health(BaseModel):
    status: Literal["ok"]
    app: str
    version: str
    environment: str


class Readiness(BaseModel):
    status: Literal["ready", "degraded"]
    checks: dict[str, str]


@router.get("/health", response_model=Health, summary="Liveness")
def health(settings: Annotated[Settings, Depends(get_settings_dependency)]) -> Health:
    return Health(
        status="ok",
        app=settings.app_name,
        version=settings.version,
        environment=settings.environment,
    )


@router.get("/health/ready", response_model=Readiness, summary="Readiness")
def readiness(
    response: Response,
    settings: Annotated[Settings, Depends(get_settings_dependency)],
    engine: Annotated[Engine, Depends(get_engine)],
) -> Readiness:
    checks: dict[str, str] = {}

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001 - the reason is reported, not raised
        checks["database"] = f"unavailable: {type(exc).__name__}"

    if settings.provider_needs_a_key and not settings.aerodatabox_api_key:
        # Worth failing readiness over. Without a key every check silently
        # becomes NEEDS_REVIEW, which looks like working software and is not.
        checks["flight_provider"] = (
            f"{settings.flight_provider} selected but no API key configured"
        )
    else:
        checks["flight_provider"] = f"{settings.flight_provider}: ok"

    if settings.email_needs_a_key and not settings.resend_api_key.strip():
        checks["email"] = "resend selected but RESEND_API_KEY is not set"
    elif settings.email_needs_a_server and not settings.smtp_host:
        # Worth failing readiness over, for the same reason as a missing API
        # key: nothing errors, nothing alerts, and every customer quietly stops
        # receiving the confirmation that tells them their claim exists.
        checks["email"] = (
            f"{settings.email_sender} selected but SMTP_HOST is not set"
        )
    else:
        checks["email"] = f"{settings.email_sender}: ok"

    # The key that encrypts identity numbers. Worth failing readiness over for
    # the sharpest reason on this list: without it EVERY OTHER PAGE WORKS, and
    # the failure arrives at the passenger step of a claim as a 500 -- the last
    # screen before somebody has finished, and the one where they have already
    # typed their identity number in.
    #
    # Settings refuses to start a deployment without one, so this should be
    # unreachable in practice. It is here because that guard was once narrowed
    # to production and this exact thing happened on staging.
    try:
        _cipher()
        checks["secrets"] = "ok"
    except SecretsUnavailable as exc:
        checks["secrets"] = f"unusable: {exc}"

    ready = all(value.endswith("ok") for value in checks.values())
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return Readiness(status="ready" if ready else "degraded", checks=checks)
