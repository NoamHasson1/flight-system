"""Tests for the health endpoints.

Liveness and readiness answer different questions, and most of these tests are
about keeping them different.
"""

from fastapi.testclient import TestClient

from app.api.deps import get_settings_dependency
from app.config import Settings
from app.main import create_app


# --- Liveness ----------------------------------------------------------------


def test_health_reports_the_running_application(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == "0.1.0"
    assert body["environment"] == "test"


def test_liveness_does_not_touch_the_database(settings: Settings) -> None:
    """The classic mistake this avoids.

    A liveness probe that checks the database restarts every instance the
    moment the database hiccups, turning a brief outage into a restart storm.
    Liveness asks "would a restart help?", and a downstream outage is the one
    case where it would not.

    Pointed at a database that cannot possibly work, /health must still say ok.
    """
    broken = settings.model_copy(update={"database_url": "sqlite:////nope/nope.db"})
    app = create_app(broken)
    app.dependency_overrides[get_settings_dependency] = lambda: broken

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200


# --- Readiness ---------------------------------------------------------------


def test_readiness_checks_the_database(client: TestClient) -> None:
    response = client.get("/health/ready")
    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"]["database"] == "ok"
    assert body["checks"]["flight_provider"] == "fake: ok"


def test_readiness_fails_when_the_database_is_unreachable(
    settings: Settings,
) -> None:
    """503, so the load balancer takes this instance out without killing it."""
    broken = settings.model_copy(update={"database_url": "sqlite:////nope/nope.db"})
    app = create_app(broken)
    app.dependency_overrides[get_settings_dependency] = lambda: broken

    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "degraded"
    assert "unavailable" in response.json()["checks"]["database"]


def test_readiness_fails_when_the_real_provider_has_no_key(
    settings: Settings,
) -> None:
    """Worth failing over, because the alternative looks like working software.

    With aerodatabox selected and no key, every lookup fails and every customer
    is told NEEDS_REVIEW. Nothing errors, nothing alerts, and the business
    quietly stops answering the only question it exists to answer.
    """
    keyless = settings.model_copy(
        update={"flight_provider": "aerodatabox", "aerodatabox_api_key": ""}
    )
    app = create_app(keyless)
    app.dependency_overrides[get_settings_dependency] = lambda: keyless

    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert "no API key" in response.json()["checks"]["flight_provider"]


def test_readiness_never_leaks_the_api_key(settings: Settings) -> None:
    """A health endpoint is usually the least-protected thing a service has."""
    configured = settings.model_copy(
        update={"flight_provider": "aerodatabox", "aerodatabox_api_key": "s3cr3t-key"}
    )
    app = create_app(configured)
    app.dependency_overrides[get_settings_dependency] = lambda: configured

    with TestClient(app) as client:
        assert "s3cr3t" not in client.get("/health/ready").text
        assert "s3cr3t" not in client.get("/health").text


# --- The application itself --------------------------------------------------


def test_the_openapi_document_is_generated(client: TestClient) -> None:
    """It is the contract the frontend will be written against, and it comes
    from the route signatures rather than from a document somebody maintains."""
    document = client.get("/openapi.json").json()
    assert document["info"]["title"] == "Flight Compensation System"
    assert "/health" in document["paths"]


def test_the_docs_are_hidden_in_production(settings: Settings) -> None:
    """Interactive docs are a gift to a developer and a map to anybody else."""
    production = settings.model_copy(update={"environment": "production"})
    app = create_app(production)

    with TestClient(app) as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 404


def test_cors_allows_the_frontend_origin(client: TestClient) -> None:
    response = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_cors_refuses_an_unknown_origin(client: TestClient) -> None:
    """Explicit origins, never "*". A wildcard with credentials is refused by
    browsers anyway, and is a bad habit to start."""
    response = client.get("/health", headers={"Origin": "https://evil.example.com"})
    assert "access-control-allow-origin" not in response.headers


def test_one_engine_is_shared_by_the_whole_process(client: TestClient, app) -> None:  # type: ignore[no-untyped-def]
    """Built once in lifespan and kept on app.state.

    An engine per request opens a fresh connection pool every time, which is the
    easiest way there is to exhaust a database.
    """
    before = app.state.engine
    client.get("/health/ready")
    client.get("/health/ready")
    assert app.state.engine is before
