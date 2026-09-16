"""Tests for the provider port and the fake adapter.

These are contract tests as much as unit tests. Everything asserted here is
something a *future* provider must also do, so when aerodatabox.py arrives in
step 11 this file is the specification it has to satisfy.
"""

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from app.domain.models import FlightStatus
from app.providers.base import (
    FlightDataProvider,
    ProviderAuthError,
    ProviderRateLimited,
    ProviderResponseInvalid,
    ProviderUnavailable,
    RawFlight,
)
from app.providers.fake import FakeFlightProvider

AUG_14 = date(2026, 8, 14)


@pytest.fixture
def provider() -> FakeFlightProvider:
    return FakeFlightProvider()


# --- The contract ------------------------------------------------------------


def test_the_fake_satisfies_the_provider_protocol(
    provider: FakeFlightProvider,
) -> None:
    """The point of the port.

    If this fails, the fake has drifted from the contract and is no longer a
    valid stand-in for the real provider -- which would make every test above
    this layer meaningless.
    """
    assert isinstance(provider, FlightDataProvider)
    assert provider.name == "fake"


async def test_fetch_returns_a_sequence_not_a_single_flight(
    provider: FakeFlightProvider,
) -> None:
    """Deliberate, and the reason is in the FR1234 scenario below."""
    flights = await provider.fetch("BA165", AUG_14)
    assert isinstance(flights, tuple)
    assert len(flights) == 1


# --- "Not found" is an answer; failure is not -------------------------------


async def test_an_unknown_flight_returns_empty_rather_than_raising(
    provider: FakeFlightProvider,
) -> None:
    """The single most important distinction in this module.

    "We looked and there is no such flight" is a 404 the customer can act on --
    usually a typo. "We could not look" is a different thing entirely and must
    never be dressed up as the first. Conflating them would let an outage read
    as "your flight does not exist".
    """
    assert await provider.fetch("XX999", AUG_14) == ()


async def test_a_flight_number_we_have_never_heard_of_also_returns_empty(
    provider: FakeFlightProvider,
) -> None:
    assert await provider.fetch("QQ4242", AUG_14) == ()


@pytest.mark.parametrize(
    ("number", "expected"),
    [
        ("ERR503", ProviderUnavailable),
        ("ERR429", ProviderRateLimited),
        ("ERR401", ProviderAuthError),
        ("ERR422", ProviderResponseInvalid),
    ],
)
async def test_failures_raise_their_own_types(
    provider: FakeFlightProvider, number: str, expected: type[Exception]
) -> None:
    """Every failure is summonable on demand.

    Real providers fail rarely and inconveniently, so error handling is the
    least-exercised code in most systems. Being able to ask for an outage means
    these paths get tested deliberately rather than by luck.

    They are distinct types because the layer above treats them the same way --
    NEEDS_REVIEW, never NOT_ELIGIBLE -- but must log and report them
    differently. An auth error is fixable in a minute; an outage is not.
    """
    with pytest.raises(expected):
        await provider.fetch(number, AUG_14)


# --- Multiple matches --------------------------------------------------------


async def test_one_number_can_match_several_flights(
    provider: FakeFlightProvider,
) -> None:
    """FR1234 flew Dublin to Stansted twice on the same day.

    Silently returning the first would tell everyone on the evening service --
    which was 4h 40m late -- that their flight was 11 minutes late. The caller
    has to ask which was theirs, and it can only do that if the provider hands
    back both.
    """
    flights = await provider.fetch("FR1234", AUG_14)
    assert len(flights) == 2
    assert flights[0].actual_departure != flights[1].actual_departure


# --- Normalisation -----------------------------------------------------------


@pytest.mark.parametrize("number", ["ba165", " BA165 ", "Ba165"])
async def test_flight_numbers_are_normalised(
    provider: FakeFlightProvider, number: str
) -> None:
    """Customers type what they type."""
    flights = await provider.fetch(number, AUG_14)
    assert len(flights) == 1
    assert flights[0].flight_number == "BA165"


async def test_the_same_number_on_a_different_date_is_a_different_flight(
    provider: FakeFlightProvider,
) -> None:
    """BA165 is 4h late on the 14th and 9h late on the 20th.

    The date is half of the key. A provider that ignored it would answer every
    query about a route with whichever day happened to be cached.
    """
    on_14 = (await provider.fetch("BA165", AUG_14))[0]
    on_20 = (await provider.fetch("BA165", date(2026, 8, 20)))[0]
    assert on_14.actual_arrival != on_20.actual_arrival


async def test_a_wildcard_scenario_matches_any_date(
    provider: FakeFlightProvider,
) -> None:
    """Keeps the demo fixtures from going stale as dates roll past."""
    for day in (date(2026, 1, 1), date(2027, 12, 31)):
        assert await provider.fetch("XX999", day) == ()
        with pytest.raises(ProviderUnavailable):
            await provider.fetch("ERR503", day)


# --- RawFlight ---------------------------------------------------------------


async def test_timestamps_are_timezone_aware(provider: FakeFlightProvider) -> None:
    """Enforced at the edge, where the data enters.

    FlightFacts refuses naive datetimes downstream, but catching it here names
    the provider and the field that produced it instead of failing three layers
    later with no context.
    """
    flight = (await provider.fetch("BA165", AUG_14))[0]
    for value in (
        flight.scheduled_departure,
        flight.actual_departure,
        flight.scheduled_arrival,
        flight.actual_arrival,
    ):
        assert value is not None
        assert value.utcoffset() is not None


def test_raw_flight_rejects_naive_timestamps() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        RawFlight(
            flight_number="BA165", flight_date=AUG_14,
            status=FlightStatus.LANDED, provider="test",
            scheduled_departure=datetime(2026, 8, 14, 2, 20),
        )


async def test_missing_fields_travel_as_none(provider: FakeFlightProvider) -> None:
    """A cancelled flight has no actual times, and the adapter must not invent
    any. Deciding what absence *means* is the mapper's job, not the provider's.
    """
    flight = (await provider.fetch("LH687", AUG_14))[0]
    assert flight.status is FlightStatus.CANCELLED
    assert flight.actual_departure is None
    assert flight.actual_arrival is None
    assert flight.scheduled_departure is not None


async def test_the_untouched_payload_is_carried_along(
    provider: FakeFlightProvider,
) -> None:
    """Stored with every check so a decision can be re-explained, or re-run
    against corrected rules, without paying the provider again."""
    flight = (await provider.fetch("BA165", AUG_14))[0]
    assert flight.raw["origin_iata"] == "TLV"
    assert flight.provider == "fake"


async def test_an_en_route_flight_has_no_arrival_time(
    provider: FakeFlightProvider,
) -> None:
    flight = (await provider.fetch("LY1", AUG_14))[0]
    assert flight.status is FlightStatus.EN_ROUTE
    assert flight.actual_departure is not None
    assert flight.actual_arrival is None


# --- The fixture file itself -------------------------------------------------


def test_every_scenario_is_loadable(provider: FakeFlightProvider) -> None:
    """A data test. A malformed scenario should fail here, at import, rather
    than halfway through a demo."""
    descriptions = provider.describe()
    assert len(descriptions) >= 12
    assert all(": " in line for line in descriptions)


def test_duplicate_scenarios_are_rejected(tmp_path: Path) -> None:
    """Two scenarios for the same key would silently shadow one another."""
    path = tmp_path / "dupes.json"
    path.write_text(
        '{"scenarios": ['
        '{"flight_number": "AA1", "date": "*", "flights": []},'
        '{"flight_number": "AA1", "date": "*", "flights": []}]}'
    )
    with pytest.raises(ValueError, match="duplicate scenario"):
        FakeFlightProvider(path)


def test_an_unknown_error_name_is_rejected(tmp_path: Path) -> None:
    """The fixture file must not be able to raise arbitrary exceptions."""
    path = tmp_path / "bad.json"
    path.write_text(
        '{"scenarios": [{"flight_number": "AA1", "date": "*", '
        '"error": "DropTheDatabase"}]}'
    )
    with pytest.raises(ValueError, match="unknown error"):
        FakeFlightProvider(path)


def test_a_scenario_timestamp_without_an_offset_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "naive.json"
    path.write_text(
        '{"scenarios": [{"flight_number": "AA1", "date": "*", "flights": ['
        '{"status": "LANDED", "scheduled_departure": "2026-08-14T02:20:00"}]}]}'
    )
    import asyncio

    with pytest.raises(ValueError, match="no UTC offset"):
        asyncio.run(FakeFlightProvider(path).fetch("AA1", AUG_14))
