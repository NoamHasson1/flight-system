"""Shared fixtures for the HTTP tests.

Every API test runs against a real application, a real in-memory database and
the fake flight provider -- no patching. FastAPI's dependency overrides are what
make that possible, and they are the reason `deps.py` exists as a separate
module rather than as imports inside each route.
"""

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_settings_dependency
from app.config import Settings
from app.db.session import create_all
from app.main import create_app


@pytest.fixture
def settings(tmp_path) -> Settings:  # type: ignore[no-untyped-def]
    """A configuration pointing at a throwaway database and the fake provider."""
    return Settings(
        environment="test",
        database_url=f"sqlite:///{tmp_path / 'api.db'}",
        upload_dir=tmp_path / "uploads",
        flight_provider="fake",
        aerodatabox_api_key="",
    )


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    application = create_app(settings)
    # get_settings() is lru_cached and would otherwise hand routes the real
    # .env-backed settings rather than the test ones.
    application.dependency_overrides[get_settings_dependency] = lambda: settings
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    # The context manager is what runs lifespan, which builds the engine.
    with TestClient(app) as test_client:
        create_all(app.state.engine)
        yield test_client
