"""Remembering an answer, and knowing when not to.

The cache saves money, and every test here is about the one way it could cost
something far more expensive than money: serving a stored prediction as though
it were a fact. A flight stored while still SCHEDULED, replayed an hour later,
reports a punctual departure for a flight that by then is six hours late --
a wrong "no" on a real claim, which is the failure this whole system is built
around.

So the rule under test throughout is: a finished flight is kept forever,
everything else is kept for minutes.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import FlightLookup
from app.db.session import create_all, create_db_engine, create_session_factory
from app.domain.models import FlightStatus
from app.providers.base import ProviderUnavailable, RawFlight
from app.providers.cache import CachingProvider, wrap_with_cache
from app.providers.chain import ChainProvider

WHEN = date(2026, 9, 18)


@pytest.fixture
def session_factory():  # type: ignore[no-untyped-def]
    """A real database, in memory.

    `StaticPool` so every session in a test sees the same in-memory database:
    the default opens a fresh, empty one per connection, and the cache reads
    and writes in separate sessions by design.
    """
    engine = create_db_engine("sqlite:///:memory:")
    create_all(engine)
    return create_session_factory(engine)


class Counting:
    """A source that records how often it was actually asked."""

    name = "test-source"

    def __init__(self, *, result: object) -> None:
        self._result = result
        self.calls = 0

    async def fetch(
        self, flight_number: str, flight_date: date
    ) -> Sequence[RawFlight]:
        self.calls += 1
        if isinstance(self._result, Exception):
            raise self._result
        return self._result  # type: ignore[return-value]


def _flight(status: FlightStatus, **overrides: object) -> RawFlight:
    base: dict[str, object] = {
        "flight_number": "BZ734",
        "flight_date": WHEN,
        "status": status,
        "provider": "test-source",
        "airline_iata": "BZ",
        "origin_iata": "TLV",
        "destination_iata": "HER",
        "scheduled_departure": datetime(2026, 9, 18, 5, 0, tzinfo=UTC),
        "actual_departure": datetime(2026, 9, 18, 8, 30, tzinfo=UTC),
    }
    base.update(overrides)
    return RawFlight(**base)  # type: ignore[arg-type]


def _cached(session_factory, source: Counting, **kwargs: object) -> CachingProvider:  # type: ignore[no-untyped-def]
    return CachingProvider(source, session_factory, **kwargs)  # type: ignore[arg-type]


# --- What may be reused ------------------------------------------------------


async def test_a_landed_flight_is_asked_for_once(session_factory) -> None:  # type: ignore[no-untyped-def]
    """The case the cache exists for.

    A cancelled or delayed flight has a planeload of passengers, and they tell
    each other. Without this, one answer is bought once per passenger.
    """
    source = Counting(result=(_flight(FlightStatus.LANDED),))
    provider = _cached(session_factory, source)

    first = await provider.fetch("BZ734", WHEN)
    second = await provider.fetch("BZ734", WHEN)

    assert source.calls == 1, "the second customer paid for the same answer"
    assert len(second) == len(first) == 1
    assert second[0].status is FlightStatus.LANDED


async def test_a_cancelled_flight_is_kept_forever(session_factory) -> None:  # type: ignore[no-untyped-def]
    """A cancellation cannot be un-cancelled, so age is irrelevant.

    The TTL is zero here: even so, the row must be served, because "settled"
    beats "fresh".
    """
    source = Counting(result=(_flight(FlightStatus.CANCELLED),))
    provider = _cached(session_factory, source, ttl=timedelta(0))

    await provider.fetch("BZ734", WHEN)
    await provider.fetch("BZ734", WHEN)

    assert source.calls == 1


async def test_a_scheduled_flight_is_asked_again(session_factory) -> None:  # type: ignore[no-untyped-def]
    """THE test in this file.

    A scheduled flight has not happened. Replaying it later would report a
    punctual departure for a flight that is by then hours late -- a confident
    "you are owed nothing" built entirely out of our own stale row.
    """
    source = Counting(result=(_flight(FlightStatus.SCHEDULED),))
    provider = _cached(session_factory, source, ttl=timedelta(0))

    await provider.fetch("BZ734", WHEN)
    await provider.fetch("BZ734", WHEN)

    assert source.calls == 2, "a prediction was served as a fact"


async def test_an_airborne_flight_is_asked_again(session_factory) -> None:  # type: ignore[no-untyped-def]
    """Same rule: it has not landed, so its arrival delay does not exist yet."""
    source = Counting(result=(_flight(FlightStatus.EN_ROUTE),))
    provider = _cached(session_factory, source, ttl=timedelta(0))

    await provider.fetch("BZ734", WHEN)
    await provider.fetch("BZ734", WHEN)

    assert source.calls == 2


async def test_an_unsettled_flight_is_reused_inside_the_ttl(session_factory) -> None:  # type: ignore[no-untyped-def]
    """The burst case: twenty people check the same flight in ten minutes.

    Nothing can have happened in that window that changes the answer, and
    twenty identical purchases is the thing being avoided.
    """
    source = Counting(result=(_flight(FlightStatus.SCHEDULED),))
    provider = _cached(session_factory, source, ttl=timedelta(minutes=15))

    await provider.fetch("BZ734", WHEN)
    await provider.fetch("BZ734", WHEN)

    assert source.calls == 1


async def test_no_such_flight_is_remembered_but_never_settled(session_factory) -> None:  # type: ignore[no-untyped-def]
    """A typo must not be re-bought on every retry, and must not be permanent.

    Empty today can become a real flight tomorrow, when the airline loads its
    schedule -- so this is cached briefly and never treated as final.
    """
    source = Counting(result=())
    fresh = _cached(session_factory, source, ttl=timedelta(minutes=15))
    await fresh.fetch("XX999", WHEN)
    await fresh.fetch("XX999", WHEN)
    assert source.calls == 1

    stale = _cached(session_factory, source, ttl=timedelta(0))
    await stale.fetch("XX999", WHEN)
    assert source.calls == 2

    with session_factory() as session:
        row = session.scalar(select(FlightLookup))
        assert row is not None
        assert row.is_final is False
        assert row.flights == []


# --- What is written ---------------------------------------------------------


async def test_the_row_survives_a_round_trip_intact(session_factory) -> None:  # type: ignore[no-untyped-def]
    """Every field the rules read has to come back the same.

    An archive that loses the actual departure time is an archive of nothing:
    that one value is the entire Israeli eligibility test.
    """
    original = _flight(FlightStatus.LANDED, actual_arrival=datetime(2026, 9, 18, 11, 0, tzinfo=UTC))
    source = Counting(result=(original,))
    provider = _cached(session_factory, source)

    await provider.fetch("BZ734", WHEN)
    restored = (await provider.fetch("BZ734", WHEN))[0]

    assert source.calls == 1
    assert restored.flight_number == original.flight_number
    assert restored.flight_date == original.flight_date
    assert restored.status is original.status
    assert restored.origin_iata == original.origin_iata
    assert restored.destination_iata == original.destination_iata
    assert restored.airline_iata == original.airline_iata
    assert restored.scheduled_departure == original.scheduled_departure
    assert restored.actual_departure == original.actual_departure
    assert restored.actual_arrival == original.actual_arrival


async def test_restored_times_are_timezone_aware(session_factory) -> None:  # type: ignore[no-untyped-def]
    """RawFlight refuses naive datetimes, and a naive/aware mix computes a
    silently wrong delay. A row that came back naive would blow up or lie."""
    source = Counting(result=(_flight(FlightStatus.LANDED),))
    provider = _cached(session_factory, source)

    await provider.fetch("BZ734", WHEN)
    restored = (await provider.fetch("BZ734", WHEN))[0]

    assert restored.actual_departure is not None
    assert restored.actual_departure.tzinfo is not None


async def test_several_flights_on_one_number_are_kept_together(session_factory) -> None:  # type: ignore[no-untyped-def]
    """One number on one date can be two flights, and the answer is both.

    Storing only the first would turn an AMBIGUOUS question into a confident
    answer about somebody else's journey.
    """
    source = Counting(
        result=(
            _flight(FlightStatus.LANDED),
            _flight(FlightStatus.LANDED, origin_iata="TLV", destination_iata="ATH"),
        )
    )
    provider = _cached(session_factory, source)

    await provider.fetch("BZ734", WHEN)
    restored = await provider.fetch("BZ734", WHEN)

    assert len(restored) == 2
    assert {f.destination_iata for f in restored} == {"HER", "ATH"}


async def test_a_settled_row_is_never_overwritten(session_factory) -> None:  # type: ignore[no-untyped-def]
    """A landed flight cannot become less landed.

    The archive's whole value rests on this. A source that has begun to forget
    a flight -- a rolling window dropping its oldest day -- must not be able to
    replace a complete row with a thin one, or the archive degrades to exactly
    the coverage of whatever answered most recently.
    """
    good = Counting(result=(_flight(FlightStatus.LANDED),))
    await _cached(session_factory, good).fetch("BZ734", WHEN)

    thin = Counting(result=())
    await _cached(session_factory, thin, ttl=timedelta(0)).fetch("BZ734", WHEN)

    with session_factory() as session:
        row = session.scalar(select(FlightLookup))
        assert row is not None
        assert row.is_final is True
        assert len(row.flights) == 1, "a settled row was replaced by an empty one"


# --- Failures ----------------------------------------------------------------


async def test_a_failing_source_writes_nothing(session_factory) -> None:  # type: ignore[no-untyped-def]
    """"The vendor is down" is not an answer, so it must not become a row.

    Caching it would turn a temporary outage into a stored "no such flight"
    that outlives the outage.
    """
    source = Counting(result=ProviderUnavailable("down"))
    provider = _cached(session_factory, source)

    with pytest.raises(ProviderUnavailable):
        await provider.fetch("BZ734", WHEN)

    with session_factory() as session:
        assert session.scalar(select(FlightLookup)) is None


# --- Wrapping a chain --------------------------------------------------------


def test_the_cache_wraps_each_source_inside_a_chain(session_factory) -> None:  # type: ignore[no-untyped-def]
    """Not around the chain.

    Rows are keyed by which source said so. Wrapping the whole chain would
    store them under "chain(aerodatabox → iaa)", which is a different question
    from the one the nightly archive answers under "iaa" -- and two spellings
    of the same fact means one of them is never read.
    """
    chain = ChainProvider([Counting(result=()), Counting(result=())])
    chain.providers[0].name = "aerodatabox"  # type: ignore[attr-defined]
    chain.providers[1].name = "iaa"  # type: ignore[attr-defined]

    wrapped = wrap_with_cache(chain, session_factory)

    assert isinstance(wrapped, ChainProvider)
    assert all(isinstance(p, CachingProvider) for p in wrapped.providers)
    assert [p.name for p in wrapped.providers] == ["aerodatabox", "iaa"]


async def test_a_cached_miss_still_lets_the_next_source_answer(session_factory) -> None:  # type: ignore[no-untyped-def]
    """The chain has to keep working through the cache.

    This is the BZ734 case exactly: the paid feed has nothing, and the free
    board does.
    """
    feed = Counting(result=())
    feed.name = "aerodatabox"  # type: ignore[attr-defined]
    board = Counting(result=(_flight(FlightStatus.CANCELLED, provider="iaa"),))
    board.name = "iaa"  # type: ignore[attr-defined]

    chain = wrap_with_cache(ChainProvider([feed, board]), session_factory)

    first = await chain.fetch("BZ734", WHEN)
    second = await chain.fetch("BZ734", WHEN)

    assert len(first) == len(second) == 1
    assert (feed.calls, board.calls) == (1, 1), "both answers were remembered"
