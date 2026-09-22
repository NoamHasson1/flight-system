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


def test_routes_use_the_settings_the_app_was_built_with(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """create_app(settings) must be authoritative for route dependencies too.

    This was a real bug. get_settings_dependency called the global, .env-backed
    get_settings(), so a route asking for configuration got whatever was on
    disk rather than what its own application was constructed with -- and an
    app built with a temporary upload directory wrote files to the one in .env.

    It hid because the engine behaved: lifespan sets that from the passed
    settings directly, so the database was always right and only the
    settings-derived dependencies were wrong.

    Deliberately no dependency_overrides here. Overriding the very dependency
    under test is what concealed this in the first place.
    """
    from app.config import Settings
    from app.main import create_app

    settings = Settings(
        environment="staging",
        database_url=f"sqlite:///{tmp_path / 'x.db'}",
        upload_dir=tmp_path / "custom-uploads",
    )
    app = create_app(settings)

    with TestClient(app) as client:
        assert client.get("/health").json()["environment"] == "staging"


def test_uploads_land_in_the_configured_directory(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """The consequence of the bug above, asserted end to end."""
    import io

    from app.config import Settings
    from app.db.session import create_all
    from app.main import create_app

    uploads = tmp_path / "custom-uploads"
    settings = Settings(
        environment="test",
        database_url=f"sqlite:///{tmp_path / 'x.db'}",
        upload_dir=uploads,
        flight_provider="fake",
    )
    app = create_app(settings)

    with TestClient(app) as client:
        create_all(app.state.engine)
        check = client.post(
            "/api/v1/eligibility/check",
            json={"flight_number": "BA165", "flight_date": "2026-08-14"},
        ).json()
        claim = client.post(
            "/api/v1/claims",
            json={
                "check_id": check["check_id"],
                "contact_name": "Noam",
                "contact_email": "n@example.com",
            },
        ).json()
        response = client.post(
            f"/api/v1/claims/{claim['id']}/documents",
            files={"file": ("r.pdf", io.BytesIO(b"%PDF-1.7 x"), "application/pdf")},
        )

    assert response.status_code == 201
    assert len(list(uploads.rglob("*.pdf"))) == 1


def test_readiness_fails_without_the_encryption_key(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """The sharpest entry on that list, and the reason it is there.

    Without this key EVERY OTHER PAGE WORKS. The failure arrives at the
    passenger step of a claim, as a 500 -- the last screen before somebody has
    finished, and the one where they have already typed their identity number
    in. Nothing else degrades, so nothing else warns.

    It happened: the guard in Settings was narrowed to production, a staging
    deployment was shown to people, and the first claim filed on it returned
    500 while the front page, the check and the result screen were all fine.
    """
    from app.db.types import configure_cipher
    from tests.conftest import TEST_ENCRYPTION_KEY

    configure_cipher("")
    try:
        app = create_app(
            Settings(
                environment="development",  # so Settings itself will start
                database_url=f"sqlite:///{tmp_path / 'x.db'}",
                encryption_keys="",
            )
        )
        with TestClient(app) as client:
            body = client.get("/health/ready").json()
        assert body["status"] == "degraded"
        assert "unusable" in body["checks"]["secrets"]
    finally:
        configure_cipher(TEST_ENCRYPTION_KEY)


def test_a_deployment_refuses_to_start_without_the_key() -> None:
    """Better than any health check: the process does not come up at all.

    Only development and test may run without one, because nobody types a real
    identity number into either.
    """
    import pytest

    from app.config import Settings

    for environment in ("staging", "production"):
        with pytest.raises(Exception, match="ENCRYPTION_KEYS"):
            Settings(environment=environment, encryption_keys="", _env_file=None)

    for environment in ("development", "test"):
        Settings(environment=environment, encryption_keys="", _env_file=None)
