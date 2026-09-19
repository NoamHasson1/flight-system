"""Asking several sources in order.

Every test here is about one distinction: the difference between "we looked and
it is not there" and "we could not look". Collapsing those two is how a system
tells somebody with a valid claim that their flight never existed.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

import pytest

from app.domain.models import FlightStatus
from app.providers.base import (
    FlightDataProvider,
    ProviderCoverageGap,
    ProviderRateLimited,
    ProviderUnavailable,
    RawFlight,
)
from app.providers.chain import ChainProvider

WHEN = date(2026, 9, 19)


def _flight(provider: str) -> RawFlight:
    return RawFlight(
        flight_number="BZ734",
        flight_date=WHEN,
        status=FlightStatus.CANCELLED,
        provider=provider,
        origin_iata="TLV",
        destination_iata="HER",
    )


class Stub:
    """A provider that does exactly one thing, and counts being asked."""

    def __init__(self, name: str, *, result: object) -> None:
        self.name = name
        self._result = result
        self.calls = 0

    async def fetch(
        self, flight_number: str, flight_date: date
    ) -> Sequence[RawFlight]:
        self.calls += 1
        if isinstance(self._result, Exception):
            raise self._result
        return self._result  # type: ignore[return-value]


def _has(name: str) -> Stub:
    return Stub(name, result=(_flight(name),))


def _empty(name: str) -> Stub:
    return Stub(name, result=())


def _broken(name: str, exc: Exception) -> Stub:
    return Stub(name, result=exc)


# --- Order -------------------------------------------------------------------


async def test_the_first_source_with_the_flight_wins() -> None:
    first, second = _has("first"), _has("second")
    flights = await ChainProvider([first, second]).fetch("BZ734", WHEN)

    assert flights[0].provider == "first"
    assert second.calls == 0, "a settled answer must not cost a second lookup"


async def test_an_empty_first_source_falls_through_to_the_second() -> None:
    """The case that prompted the chain.

    The commercial feed holds Tel Aviv but drops cancellations; the board has
    them. Neither is broken -- the first simply does not have this flight.
    """
    feed, board = _empty("aerodatabox"), _has("iaa")
    flights = await ChainProvider([feed, board]).fetch("BZ734", WHEN)

    assert flights[0].provider == "iaa"
    assert board.calls == 1


async def test_a_failing_source_is_skipped_not_fatal() -> None:
    """A dead vendor must not take the free source down with it."""
    feed = _broken("aerodatabox", ProviderUnavailable("down"))
    board = _has("iaa")

    flights = await ChainProvider([feed, board]).fetch("BZ734", WHEN)
    assert flights[0].provider == "iaa"


# --- The distinction that matters -------------------------------------------


async def test_empty_from_anyone_means_no_such_flight() -> None:
    """One source genuinely looked. The customer can act on that.

    This has to stay an empty result rather than an error, because "check the
    flight number and the date" is useful and "we could not determine" is not,
    when the number really is a typo.
    """
    board = _broken("iaa", ProviderCoverageGap("outside the window"))
    feed = _empty("aerodatabox")

    flights = await ChainProvider([board, feed]).fetch("XX999", WHEN)
    assert flights == ()


async def test_when_nobody_could_look_the_chain_raises() -> None:
    """Nobody looked, so nobody may say no.

    Returning empty here would become "we could not find that flight" on the
    screen -- a confident statement about data the system never saw. Raising
    makes it NEEDS_REVIEW instead.
    """
    feed = _broken("aerodatabox", ProviderRateLimited("quota gone"))
    board = _broken("iaa", ProviderUnavailable("data.gov.il down"))

    with pytest.raises(ProviderRateLimited):
        await ChainProvider([feed, board]).fetch("BZ734", WHEN)


async def test_the_reported_failure_is_the_first_provider_s() -> None:
    """Of several failures, report the one the operator trusted first.

    Quota exhausted on the primary source is the actionable signal; a fallback
    also being down is secondary noise.
    """
    feed = _broken("aerodatabox", ProviderRateLimited("quota gone"))
    board = _broken("iaa", ProviderUnavailable("down"))

    with pytest.raises(ProviderRateLimited) as caught:
        await ChainProvider([feed, board]).fetch("BZ734", WHEN)
    assert "quota" in str(caught.value)


# --- Shape -------------------------------------------------------------------


async def test_every_source_is_asked_before_giving_up() -> None:
    a, b, c = _empty("a"), _empty("b"), _has("c")
    flights = await ChainProvider([a, b, c]).fetch("BZ734", WHEN)

    assert flights[0].provider == "c"
    assert (a.calls, b.calls, c.calls) == (1, 1, 1)


def test_the_name_shows_the_order() -> None:
    """It is logged and stored with every check; it has to say which order."""
    chain = ChainProvider([_empty("aerodatabox"), _empty("iaa")])
    assert chain.name == "chain(aerodatabox → iaa)"


def test_an_empty_chain_is_refused_at_construction() -> None:
    """A misconfiguration that would otherwise fail one request at a time."""
    with pytest.raises(ValueError):
        ChainProvider([])


def test_a_chain_satisfies_the_provider_contract() -> None:
    assert isinstance(ChainProvider([_empty("a")]), FlightDataProvider)
