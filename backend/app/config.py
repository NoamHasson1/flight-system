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

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.email.registry import AVAILABLE as EMAIL_SENDERS
from app.email.registry import CONSOLE, RESEND, SMTP
from app.providers.registry import AVAILABLE, CHAIN_SEPARATOR, FAKE, IAA


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

    # --- secrets ---
    # Encrypts passengers' national identity numbers at rest. Comma-separated
    # to allow rotation: the first key encrypts, every key can decrypt.
    #
    # Empty is allowed so the system runs before anybody has collected an
    # identity document -- but the first attempt to store one then fails
    # loudly rather than writing plaintext, and production refuses to start
    # without it.
    encryption_keys: str = ""

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

    # Reuse a source's answer instead of buying it twice.
    #
    # A settled flight -- landed, cancelled, diverted -- is kept forever,
    # because it cannot change. Anything still in motion is kept for
    # `flight_cache_ttl_minutes` only: serving a stored "SCHEDULED" as though
    # it were fact is how a flight that went on to be six hours late gets
    # reported as punctual.
    flight_cache: bool = True
    flight_cache_ttl_minutes: int = 15

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

    # --- email ---
    #
    # Defaults to "console", which writes messages to the log instead of
    # sending them. Same reasoning as the fake flight provider: the system
    # runs and is demonstrable with no mail account, and nobody can
    # accidentally send a real message to a real person while developing.
    email_sender: str = CONSOLE
    email_from: str = "Skyclaim <noreply@example.com>"

    # Where the company hears about its own business.
    #
    # Every check and every claim is copied here, so the people who chase
    # airlines can work from an inbox rather than from a database -- the person
    # who writes a claim letter is not the person who writes SQL.
    #
    # Empty switches it off entirely, which is right for a laptop and wrong for
    # a deployment.
    ops_email: str = ""

    # Whether every CHECK is copied, or only claims.
    #
    # On, because early on every check is worth seeing and the volume is a
    # handful a day. Turn it off when that stops being true: an inbox nobody
    # reads is worse than no inbox, and the claims are the part that is work.
    ops_notify_checks: bool = True

    # Resend, for hosts that close the SMTP ports -- which is most of them.
    # Render, Fly and the rest shut 25, 465 and 587, because a rented container
    # that can open an SMTP connection is a spam relay waiting to be found.
    # Port 443 is open, so mail goes over an HTTP API instead.
    resend_api_key: str = ""

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = True
    smtp_ssl: bool = False

    # Where the links in emails point. Not derivable from a request: a
    # background task has no request, and behind a proxy the request's own host
    # is the proxy's, not the one the customer typed.
    public_base_url: str = "http://localhost:3111"

    # --- the admin API ---
    #
    # Empty by default, and an empty key means the admin API is CLOSED rather
    # than open. Failing closed is the only safe default for an endpoint that
    # lists every customer's name, email address and national identity number:
    # a system that ships unprotected because somebody forgot a variable is a
    # breach waiting for someone to notice the URL.
    admin_api_key: str = ""

    log_level: str = "INFO"

    # The readable request trace: input, the API call, what came back, what we
    # normalised it to, each law's answer, the decision, and every database
    # write. Genuinely useful while building and far too noisy in production,
    # so it is on by default and off when the environment is production.
    log_flow: bool = True

    @field_validator("flight_provider")
    @classmethod
    def _known_provider(cls, value: str) -> str:
        """Catch a typo'd provider name at boot.

        Otherwise it surfaces as a failed lookup during a real check, which the
        customer sees as NEEDS_REVIEW -- a silent degradation nobody notices
        for days.
        """
        wanted = value.strip().lower()
        parts = [p.strip() for p in wanted.split(CHAIN_SEPARATOR) if p.strip()]
        unknown = [p for p in parts if p not in AVAILABLE]
        if not parts or unknown:
            raise ValueError(
                f"unknown flight_provider {value!r}; available: "
                f"{', '.join(AVAILABLE)}, or several joined by "
                f"{CHAIN_SEPARATOR!r} such as 'aerodatabox{CHAIN_SEPARATOR}iaa'"
            )
        return CHAIN_SEPARATOR.join(parts)

    @model_validator(mode="after")
    def _deployments_have_a_key(self) -> "Settings":
        """Refuse to start ANY deployment with no encryption key.

        The alternative is a service that runs perfectly until the first person
        types their identity number, and fails then -- in front of them, at the
        worst moment, for a reason nobody on the deploy remembers choosing.

        This originally said `production` only, and that was wrong in exactly
        the way the paragraph above describes. A staging deployment shown to
        real people is a deployment: the first claim anybody filed on it
        returned 500 at the passenger step, while every other page worked, and
        the error the customer saw blamed the flight database. Narrowing a
        guard to production is how it fails to guard the thing you actually
        showed somebody.

        Only development and test may run without a key, because nobody types
        a real identity number into either.
        """
        deployed = self.environment not in ("development", "test")
        if deployed and not self.encryption_keys.strip():
            raise ValueError(
                f"ENCRYPTION_KEYS must be set when environment is "
                f"{self.environment!r}: identity numbers are encrypted at rest "
                f"and cannot be stored without it. Generate one with\n"
                f'  python -c "from cryptography.fernet import Fernet; '
                f'print(Fernet.generate_key().decode())"'
            )
        return self

    @field_validator("email_sender")
    @classmethod
    def _known_email_sender(cls, value: str) -> str:
        if value.strip().lower() not in EMAIL_SENDERS:
            raise ValueError(
                f"unknown email_sender {value!r}; available: "
                f"{', '.join(EMAIL_SENDERS)}"
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
    def flow_logging_enabled(self) -> bool:
        """On unless explicitly disabled, and never in production.

        The trace prints customer emails (masked) and flight details on every
        request. That is exactly what you want on a laptop and exactly what you
        do not want accumulating in a production log aggregator.
        """
        return self.log_flow and not self.is_production

    @property
    def email_needs_a_key(self) -> bool:
        return self.email_sender == RESEND

    @property
    def email_needs_a_server(self) -> bool:
        """SMTP specifically, not "anything that is not the console".

        It said `!= CONSOLE`, which was true while there were only two
        senders, and became wrong the moment a third arrived that speaks HTTP
        and has no server to name. A correctly configured Resend deployment
        reported itself degraded for want of SMTP_HOST -- a setting it will
        never have.

        The lesson is the shape of the test: asking what something is NOT
        stops being true the moment the set grows.
        """
        return self.email_sender == SMTP

    @property
    def admin_api_enabled(self) -> bool:
        return bool(self.admin_api_key.strip())

    @property
    def provider_needs_a_key(self) -> bool:
        """True when any source in play bills for a key.

        A chain can mix a keyed source with a free one, so this asks whether
        ANY member needs a key -- one that does makes the key required.
        """
        parts = self.flight_provider.split(CHAIN_SEPARATOR)
        return any(part not in (FAKE, IAA) for part in parts)

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
            "email_sender": self.email_sender,
            "database": self.database_url.split("://", 1)[0],
        }


@lru_cache
def get_settings() -> Settings:
    """Cached so the .env file is read once, and so tests can override it in a
    single place with FastAPI's dependency overrides."""
    return Settings()
