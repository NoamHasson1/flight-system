"""Tests for configuration.

The value of validating settings is that a mistake stops the process at boot,
with a message naming the field, instead of surfacing an hour later as a
confusing failure on a customer's first request.
"""

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_a_typo_in_the_provider_name_fails_at_startup() -> None:
    """Otherwise it surfaces as a failed lookup during a real check, which the
    customer sees as NEEDS_REVIEW -- a silent degradation nobody notices for
    days."""
    with pytest.raises(ValidationError, match="unknown flight_provider"):
        Settings(flight_provider="aerodatabax")


def test_an_unknown_environment_is_rejected() -> None:
    with pytest.raises(ValidationError, match="environment must be one of"):
        Settings(environment="prodution")


def test_the_provider_defaults_to_the_fake() -> None:
    """So that starting this application without an API key gives you a working
    system rather than a broken one."""
    assert Settings().flight_provider == "fake"


def test_describe_never_includes_the_api_key() -> None:
    """Absent rather than masked: a masked secret in a log is still a secret in
    a log, one careless change away from being unmasked."""
    settings = Settings(aerodatabox_api_key="s3cr3t-key")
    assert "s3cr3t" not in str(settings.describe())
    assert "aerodatabox_api_key" not in settings.describe()


def test_provider_needs_a_key_only_for_the_real_one() -> None:
    assert Settings(flight_provider="fake").provider_needs_a_key is False
    assert Settings(flight_provider="aerodatabox").provider_needs_a_key is True


def test_environment_and_provider_names_are_normalised() -> None:
    settings = Settings(environment="  PRODUCTION ", flight_provider=" FAKE ")
    assert settings.environment == "production"
    assert settings.flight_provider == "fake"
    assert settings.is_production is True


def test_the_log_level_is_actually_applied() -> None:
    """It was declared for several steps before anything read it.

    A setting nobody reads is worse than no setting: it looks configurable, so
    somebody changes it, and nothing happens. Meanwhile the real level is
    whatever the last library to touch logging decided -- Alembic's fileConfig
    sets the root logger to WARN, which would have silently swallowed every
    INFO message the application writes, including "we could not send email".
    """
    import logging

    from app.main import create_app

    create_app(Settings(environment="test", log_level="DEBUG"))
    app_logger = logging.getLogger("flight_system")

    assert app_logger.level == logging.DEBUG
    # Its own handler and no propagation, so another library reconfiguring the
    # root logger cannot decide whether our messages appear.
    assert app_logger.handlers
    assert app_logger.propagate is False
