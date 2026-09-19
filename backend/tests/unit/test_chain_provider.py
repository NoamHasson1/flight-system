"""Asking several sources in order.

Every test here is about one distinction: the difference between "we looked and
it is not there" and "we could not look". Collapsing those two is how a system
tells somebody with a valid claim that their flight never existed.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime

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


def _flight(provider: str, **overrides: object) -> RawFlight:
    """A complete record: both ends of the journey described.

    Both ends matter to the chain, not just for realism. A record that knows
    only one end is deliberately NOT a finished answer -- the chain goes on to
    ask the next source for the other half -- so a stub missing them would
    silently be testing the completion path instead of the one it names.
    """
    base: dict[str, object] = {
        "flight_number": "BZ734",
        "flight_date": WHEN,
        "status": FlightStatus.CANCELLED,
        "provider": provider,
        "origin_iata": "TLV",
        "destination_iata": "HER",
        "scheduled_departure": datetime(2026, 9, 19, 5, 0, tzinfo=UTC),
        "scheduled_arrival": datetime(2026, 9, 19, 7, 30, tzinfo=UTC),
    }
    base.update(overrides)
    return RawFlight(**base)  # type: ignore[arg-type]


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


# --- A record that cannot be used is not an answer ---------------------------


def _unrouted(name: str) -> Stub:
    """A codeshare record: departure known, destination only a name."""
    return Stub(
        name,
        result=(
            RawFlight(
                flight_number="AC5520",
                flight_date=WHEN,
                status=FlightStatus.EN_ROUTE,
                provider=name,
                origin_iata="TLV",
                destination_iata=None,
            ),
        ),
    )


def _impossible(name: str) -> Stub:
    """IZ216 as the vendor actually returned it on 14 September.

    Scheduled arrival a day BEFORE the scheduled departure. One of the two is
    wrong and the record cannot say which, so a departure delay computed from
    it is out by twenty-two hours -- in the direction that denies a real claim.
    """
    return Stub(
        name,
        result=(
            RawFlight(
                flight_number="IZ216",
                flight_date=WHEN,
                status=FlightStatus.LANDED,
                provider=name,
                origin_iata="ATH",
                destination_iata="TLV",
                scheduled_departure=datetime(2026, 9, 19, 21, 25, tzinfo=UTC),
                scheduled_arrival=datetime(2026, 9, 19, 0, 35, tzinfo=UTC),
            ),
        ),
    )


async def test_a_codeshare_without_a_destination_falls_through() -> None:
    """Found is not the same as usable.

    Without both ends there is no country pair and no distance, so no law can
    be tested and no amount computed. The next source may know the route.
    """
    thin, complete = _unrouted("aerodatabox"), _has("iaa")
    flights = await ChainProvider([thin, complete]).fetch("AC5520", WHEN)

    assert flights[0].provider == "iaa"
    assert complete.calls == 1


async def test_a_record_that_contradicts_itself_falls_through() -> None:
    """The real IZ216 case."""
    broken, good = _impossible("aerodatabox"), _has("iaa")
    flights = await ChainProvider([broken, good]).fetch("IZ216", WHEN)

    assert flights[0].provider == "iaa"


async def test_an_unusable_record_is_still_better_than_nothing() -> None:
    """When nobody does better, return what we have.

    "We could not identify this flight -- the arrival time is not after the
    departure time" tells a person what to look at. "No such flight" sends a
    passenger away from a flight that plainly exists.
    """
    thin = _unrouted("aerodatabox")
    empty = _empty("iaa")

    flights = await ChainProvider([thin, empty]).fetch("AC5520", WHEN)
    assert len(flights) == 1
    assert flights[0].provider == "aerodatabox"


async def test_a_usable_record_still_wins_immediately() -> None:
    """The check must not cost an extra lookup on the ordinary path."""
    good, other = _has("aerodatabox"), _has("iaa")
    await ChainProvider([good, other]).fetch("BZ734", WHEN)
    assert other.calls == 0


# --- Filling in the half a source does not have ------------------------------
#
# The Ben Gurion board records the movement AT Ben Gurion: a departure row
# knows the take-off and never learns the landing. That is enough for the
# Israeli law, which measures at departure, and not enough for EC261, which
# measures at arrival -- so half of every route's claims would be invisible if
# the chain stopped at the first source that had the flight.


def _departure_only(name: str) -> Stub:
    """A board record: take-off known, landing unknown."""
    return Stub(
        name,
        result=(
            _flight(name, scheduled_arrival=None, actual_arrival=None,
                    status=FlightStatus.LANDED,
                    actual_departure=datetime(2026, 9, 19, 8, 0, tzinfo=UTC)),
        ),
    )


def _full(name: str) -> Stub:
    return Stub(
        name,
        result=(
            _flight(name, status=FlightStatus.LANDED,
                    actual_departure=datetime(2026, 9, 19, 9, 9, tzinfo=UTC),
                    actual_arrival=datetime(2026, 9, 19, 11, 0, tzinfo=UTC)),
        ),
    )


async def test_the_missing_half_is_filled_from_the_next_source() -> None:
    """The board knows the departure; the feed supplies the landing.

    Without this an EC261 claim on a Tel Aviv departure can never be priced,
    because the amount turns on how late the passenger actually arrived.
    """
    board, feed = _departure_only("iaa"), _full("aerodatabox")
    flights = await ChainProvider([board, feed]).fetch("BZ734", WHEN)

    assert len(flights) == 1
    assert flights[0].actual_arrival is not None, "the far half was not filled"
    assert feed.calls == 1


async def test_the_first_source_is_never_overwritten() -> None:
    """Only empty fields are filled.

    The board is the airport's own record of what happened at that airport, and
    the commercial feed has already been caught mis-dating exactly these
    flights. Where they disagree, the airport wins.
    """
    board, feed = _departure_only("iaa"), _full("aerodatabox")
    flights = await ChainProvider([board, feed]).fetch("BZ734", WHEN)

    assert flights[0].actual_departure == datetime(2026, 9, 19, 8, 0, tzinfo=UTC)
    assert flights[0].provider == "iaa"


async def test_a_complete_record_costs_no_second_lookup() -> None:
    """Completion must not turn every check into two API calls."""
    board, feed = _full("iaa"), _full("aerodatabox")
    await ChainProvider([board, feed]).fetch("BZ734", WHEN)
    assert feed.calls == 0


async def test_times_are_not_borrowed_from_a_different_leg() -> None:
    """A number covering two routes must not lend one leg's times to the other.

    Guessing which leg to borrow from is how one passenger's delay gets
    attached to another passenger's flight -- and then paid out, or refused, on
    that basis.
    """
    board = _departure_only("iaa")
    elsewhere = Stub(
        "aerodatabox",
        result=(
            _flight("aerodatabox", origin_iata="TLV", destination_iata="ATH",
                    actual_arrival=datetime(2026, 9, 19, 12, 0, tzinfo=UTC)),
        ),
    )
    flights = await ChainProvider([board, elsewhere]).fetch("BZ734", WHEN)

    assert flights[0].actual_arrival is None, "times came from the wrong leg"


async def test_a_source_that_cannot_fill_it_in_is_not_fatal() -> None:
    """Half an answer beats none.

    A Tel Aviv departure with only a take-off time still settles the Israeli
    question outright, so an unreachable second source must not lose it.
    """
    board = _departure_only("iaa")
    broken = _broken("aerodatabox", ProviderUnavailable("down"))

    flights = await ChainProvider([board, broken]).fetch("BZ734", WHEN)
    assert len(flights) == 1
    assert flights[0].actual_departure is not None


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
