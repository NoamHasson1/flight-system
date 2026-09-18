"""Configuration, validated once at startup.

Every setting is read from the environment (or a .env file) and checked when the
application boots. A bad value should stop the process immediately with a
message naming the field -- not surface as a confusing failure on a customer's
first request an hour later.

Nothing here has a secret as its default. The nearest thing to a dangerous
default is the provider, which defaults to "fake" precisely so that starting
this application without an API key gives you a working system rather than a
broken one.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.providers.registry import AVAILABLE, FAKE


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # an unknown variable in the environment is not an error
    )

    # --- identity ---
    app_name: str = "Flight Compensation System"
    version: str = "0.1.0"
    environment: str = Field(
        default="development",
        description="development | staging | production",
    )

    # --- storage ---
    database_url: str = "sqlite:///./flight_system.db"
    upload_dir: Path = Path("storage/uploads")

    # --- flight data ---
    flight_provider: str = Field(
        default=FAKE,
        description=(
            "Which adapter to use. Defaults to the fake so the system runs "
            "without a subscription."
        ),
    )
    aerodatabox_api_key: str = ""

    # --- the frontend ---
    # Explicit origins, never "*". A wildcard with credentials is both refused
    # by browsers and a bad habit to start.
    # 3000 is Next's default; 3111 is the fallback this project uses when 3000
    # is already taken. Both loopback spellings, because a browser treats
    # localhost and 127.0.0.1 as different origins and people type both.
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3111",
        "http://127.0.0.1:3111",
    ]

    # --- the admin API ---
    #
    # Empty by default, and an empty key means the admin API is CLOSED rather
    # than open. Failing closed is the only safe default for an endpoint that
    # lists every customer's name, email address and national identity number:
    # a system that ships unprotected because somebody forgot a variable is a
    # breach waiting for someone to notice the URL.
    admin_api_key: str = ""

    log_level: str = "INFO"

    @field_validator("flight_provider")
    @classmethod
    def _known_provider(cls, value: str) -> str:
        """Catch a typo'd provider name at boot.

        Otherwise it surfaces as a failed lookup during a real check, which the
        customer sees as NEEDS_REVIEW -- a silent degradation nobody notices
        for days.
        """
        if value.strip().lower() not in AVAILABLE:
            raise ValueError(
                f"unknown flight_provider {value!r}; available: {', '.join(AVAILABLE)}"
            )
        return value.strip().lower()

    @field_validator("environment")
    @classmethod
    def _known_environment(cls, value: str) -> str:
        allowed = {"development", "staging", "production", "test"}
        if value.strip().lower() not in allowed:
            raise ValueError(f"environment must be one of {sorted(allowed)}")
        return value.strip().lower()

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def admin_api_enabled(self) -> bool:
        return bool(self.admin_api_key.strip())

    @property
    def provider_needs_a_key(self) -> bool:
        return self.flight_provider != FAKE

    def describe(self) -> dict[str, object]:
        """Settings that are safe to log or expose.

        The API key is deliberately absent rather than masked: a masked secret
        in a log is still a secret in a log, one careless change away from
        being unmasked.
        """
        return {
            "app_name": self.app_name,
            "version": self.version,
            "environment": self.environment,
            "flight_provider": self.flight_provider,
            "database": self.database_url.split("://", 1)[0],
        }


@lru_cache
def get_settings() -> Settings:
    """Cached so the .env file is read once, and so tests can override it in a
    single place with FastAPI's dependency overrides."""
    return Settings()
