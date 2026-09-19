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
from app.providers.chain import ChainProvider
from app.providers.fake import FakeFlightProvider
from app.providers.iaa import IsraelAirportsProvider

FAKE = "fake"
AERODATABOX = "aerodatabox"
IAA = "iaa"

# A chain is written as its members joined by "+", so a deployment can reorder
# or drop a source without a code change:
#
#     FLIGHT_PROVIDER=aerodatabox+iaa     both, global feed first
#     FLIGHT_PROVIDER=iaa+aerodatabox     both, free source first
#     FLIGHT_PROVIDER=iaa                 Israel only, no key needed
CHAIN_SEPARATOR = "+"


def _build_fake(api_key: str | None) -> FlightDataProvider:
    return FakeFlightProvider()


def _build_aerodatabox(api_key: str | None) -> FlightDataProvider:
    return AeroDataBoxProvider(api_key or "")


def _build_iaa(api_key: str | None) -> FlightDataProvider:
    # No key: the Ben Gurion board is published openly by the state.
    return IsraelAirportsProvider()


_BUILDERS: dict[str, Callable[[str | None], FlightDataProvider]] = {
    FAKE: _build_fake,
    AERODATABOX: _build_aerodatabox,
    IAA: _build_iaa,
}

AVAILABLE: tuple[str, ...] = tuple(sorted(_BUILDERS))


def build_provider(name: str, *, api_key: str | None = None) -> FlightDataProvider:
    """Construct the named provider.

    Raises ValueError -- not a provider error -- for an unknown name. A
    misconfigured provider name is a deployment mistake that should stop the
    application at startup, not degrade into failed lookups at request time.
    """
    wanted = name.strip().lower()

    if CHAIN_SEPARATOR in wanted:
        parts = [p.strip() for p in wanted.split(CHAIN_SEPARATOR) if p.strip()]
        if len(parts) < 2:
            raise ValueError(
                f"{name!r} is not a usable chain; write it as "
                f"'aerodatabox{CHAIN_SEPARATOR}iaa'"
            )
        return ChainProvider([build_provider(p, api_key=api_key) for p in parts])

    try:
        build = _BUILDERS[wanted]
    except KeyError:
        raise ValueError(
            f"unknown flight data provider {name!r}; available: "
            f"{', '.join(AVAILABLE)} (or several joined by "
            f"{CHAIN_SEPARATOR!r})"
        ) from None
    return build(api_key)
