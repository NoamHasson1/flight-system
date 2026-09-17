"""Selecting a flight-data provider by name.

The single place that knows which adapters exist. Everything else asks for a
provider by name and receives something satisfying `FlightDataProvider` -- so
changing provider is a configuration change, not a code change.

    provider = build_provider("aerodatabox", api_key=settings.api_key)
    provider = build_provider("fake")           # no key, no network

Adding a third provider means writing its adapter and adding one line here.
"""

from __future__ import annotations

from collections.abc import Callable

from app.providers.aerodatabox import AeroDataBoxProvider
from app.providers.base import FlightDataProvider
from app.providers.fake import FakeFlightProvider

FAKE = "fake"
AERODATABOX = "aerodatabox"


def _build_fake(api_key: str | None) -> FlightDataProvider:
    return FakeFlightProvider()


def _build_aerodatabox(api_key: str | None) -> FlightDataProvider:
    return AeroDataBoxProvider(api_key or "")


_BUILDERS: dict[str, Callable[[str | None], FlightDataProvider]] = {
    FAKE: _build_fake,
    AERODATABOX: _build_aerodatabox,
}

AVAILABLE: tuple[str, ...] = tuple(sorted(_BUILDERS))


def build_provider(name: str, *, api_key: str | None = None) -> FlightDataProvider:
    """Construct the named provider.

    Raises ValueError -- not a provider error -- for an unknown name. A
    misconfigured provider name is a deployment mistake that should stop the
    application at startup, not degrade into failed lookups at request time.
    """
    try:
        build = _BUILDERS[name.strip().lower()]
    except KeyError:
        raise ValueError(
            f"unknown flight data provider {name!r}; available: "
            f"{', '.join(AVAILABLE)}"
        ) from None
    return build(api_key)
