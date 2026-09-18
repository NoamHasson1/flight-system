"""Test-wide isolation.

One job: stop the suite from reading the developer's own .env.

`Settings()` loads .env by default, which is right for the application and
wrong for tests. Without this, a test asserting a code default is really
asserting whatever happens to be on the machine running it -- and the suite
passes or fails depending on who checked it out. That is not hypothetical: the
test asserting the provider defaults to "fake" passed for weeks and then broke
the moment a real AeroDataBox key was configured locally, which is exactly the
wrong time for a test to start failing.

Disabling the env file makes every test see the defaults declared in the code
unless it overrides them explicitly, which is what a test should be asserting.
"""

from __future__ import annotations

import pytest

from app.config import Settings, get_settings

# Variables pydantic-settings would otherwise pick up straight from the
# environment, .env aside -- a shell that exported one would defeat the point.
_LEAKY = (
    "ENVIRONMENT",
    "DATABASE_URL",
    "UPLOAD_DIR",
    "FLIGHT_PROVIDER",
    "AERODATABOX_API_KEY",
    "ADMIN_API_KEY",
    "CORS_ORIGINS",
    "LOG_LEVEL",
)


@pytest.fixture(autouse=True)
def _isolate_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test sees the code's defaults, never the machine's."""
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    for name in _LEAKY:
        monkeypatch.delenv(name, raising=False)
    # get_settings is lru_cached; a value cached from a previous test's
    # environment would outlive the monkeypatch.
    get_settings.cache_clear()
