"""The list of flights somebody is owed money for.

A report over the archive, so the tests are about what it must not do to the
reader: hide a claim, double-count one, or quietly pick one source's answer
over another's without saying so.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from app.db.models import FlightLookup
from app.db.session import create_all, create_db_engine, create_session_factory
from app.domain.models import FlightStatus
from app.providers.base import RawFlight
from app.providers.cache import encode, now
from app.tasks.disruptions import find

TODAY = datetime.now(UTC).date()
YESTERDAY = TODAY - timedelta(days=1)


@pytest.fixture
def session_factory():  # type: ignore[no-untyped-def]
    engine = create_db_engine("sqlite:///:memory:")
    create_all(engine)
    return create_session_factory(engine)


def _store(session_factory, provider: str, *flights: RawFlight) -> None:  # type: ignore[no-untyped-def]
    with session_factory() as session:
        for flight in flights:
            session.add(
                FlightLookup(
                    provider=provider,
                    flight_number=flight.flight_number,
                    flight_date=flight.flight_date,
                    observed_at=now(),
                    is_final=True,
                    flights=[encode(flight)],
                )
            )
        session.commit()


def _flight(
    number: str,
    *,
    status: FlightStatus = FlightStatus.LANDED,
    origin: str = "TLV",
    destination: str = "HER",
    airline: str = "BZ",
    delay_hours: float | None = None,
    when: date | None = None,
    provider: str = "iaa",
) -> RawFlight:
    day = when or YESTERDAY
    scheduled = datetime(day.year, day.month, day.day, 5, 0, tzinfo=UTC)
    actual = (
        scheduled + timedelta(hours=delay_hours) if delay_hours is not None else None
    )
    return RawFlight(
        flight_number=number,
        flight_date=day,
        status=status,
        provider=provider,
        airline_iata=airline,
        origin_iata=origin,
        destination_iata=destination,
        scheduled_departure=scheduled,
        actual_departure=actual,
    )


# --- What counts as a disruption ---------------------------------------------


def test_a_cancellation_is_listed_even_with_no_times(session_factory) -> None:  # type: ignore[no-untyped-def]
    """Cancellations have no delay to measure and are the most valuable rows
    in the report. A filter written only around delay hours drops every one."""
    _store(session_factory, "iaa", _flight("BZ734", status=FlightStatus.CANCELLED))

    found = find(session_factory, min_delay_hours=3.0)

    assert len(found) == 1
    assert found[0].flight_number == "BZ734"
    assert found[0].status == "CANCELLED"


def test_a_short_delay_is_left_out(session_factory) -> None:  # type: ignore[no-untyped-def]
    """Nobody is owed anything for forty minutes, and a report that lists
    every flight is a report nobody reads."""
    _store(session_factory, "iaa", _flight("BZ100", delay_hours=0.7))
    assert find(session_factory, min_delay_hours=3.0) == []


def test_the_threshold_is_the_operator_s_to_choose(session_factory) -> None:  # type: ignore[no-untyped-def]
    """Three hours finds EC261 claims; eight finds only Israeli ones."""
    _store(session_factory, "iaa", _flight("BZ200", delay_hours=4.0))

    assert len(find(session_factory, min_delay_hours=3.0)) == 1
    assert find(session_factory, min_delay_hours=8.0) == []


def test_flights_older_than_the_window_are_left_out(session_factory) -> None:  # type: ignore[no-untyped-def]
    _store(
        session_factory,
        "iaa",
        _flight("BZ300", delay_hours=9.0, when=TODAY - timedelta(days=40)),
    )
    assert find(session_factory, days=7) == []
    assert len(find(session_factory, days=90)) == 1


# --- One row per flight ------------------------------------------------------


def test_a_flight_both_sources_hold_is_listed_once(session_factory) -> None:  # type: ignore[no-untyped-def]
    """Both sources carry most Tel Aviv flights. Listing each twice makes a
    comparison table twice as long and half as readable."""
    _store(session_factory, "iaa", _flight("BZ400", delay_hours=9.0))
    _store(
        session_factory,
        "aerodatabox",
        _flight("BZ400", delay_hours=9.0, provider="aerodatabox"),
    )

    found = find(session_factory)
    assert len(found) == 1


def test_a_disagreement_between_sources_is_shown_not_hidden(session_factory) -> None:  # type: ignore[no-untyped-def]
    """The most useful thing this report can surface.

    One source prices the flight; the other cannot see far enough to judge it.
    The better-informed answer is kept, and the fact that they differed is
    printed -- it is either a data problem worth chasing or a bug worth fixing,
    and both are cheaper to find here than in front of a customer.
    """
    # The board knows only the Tel Aviv end, so its record cannot be judged.
    blind = RawFlight(
        flight_number="BZ500",
        flight_date=YESTERDAY,
        status=FlightStatus.LANDED,
        provider="iaa",
        airline_iata="BZ",
        origin_iata="TLV",
        destination_iata="ZZZ",  # not in our reference data -> NEEDS_REVIEW
        scheduled_departure=datetime(
            YESTERDAY.year, YESTERDAY.month, YESTERDAY.day, 5, 0, tzinfo=UTC
        ),
        actual_departure=datetime(
            YESTERDAY.year, YESTERDAY.month, YESTERDAY.day, 14, 0, tzinfo=UTC
        ),
    )
    _store(session_factory, "iaa", blind)
    _store(
        session_factory,
        "aerodatabox",
        _flight("BZ500", delay_hours=9.0, provider="aerodatabox"),
    )

    found = find(session_factory)

    assert len(found) == 1
    assert found[0].verdict == "LIKELY_ELIGIBLE"
    assert "≠" in found[0].source, "the sources disagreed and nobody was told"
    assert "iaa" in found[0].source


# --- Order -------------------------------------------------------------------


def test_the_biggest_claims_are_at_the_top(session_factory) -> None:  # type: ignore[no-untyped-def]
    """Read top-down, this is a list in order of what is owed."""
    _store(
        session_factory,
        "iaa",
        _flight("BZ600", delay_hours=4.0),
        _flight("BZ601", delay_hours=12.0),
        _flight("BZ602", status=FlightStatus.CANCELLED),
    )

    order = [d.flight_number for d in find(session_factory)]
    assert order == ["BZ602", "BZ601", "BZ600"]


# --- Which end the delay was measured at -------------------------------------


def test_the_report_says_which_clock_it_read(session_factory) -> None:  # type: ignore[no-untyped-def]
    """Israeli law reads the departure and EC261 reads the arrival.

    Anyone comparing this against another service needs to know which number
    they are looking at, or two correct systems will look like they disagree.
    """
    arriving = RawFlight(
        flight_number="BZ700",
        flight_date=YESTERDAY,
        status=FlightStatus.LANDED,
        provider="iaa",
        airline_iata="BZ",
        origin_iata="HER",
        destination_iata="TLV",
        scheduled_arrival=datetime(
            YESTERDAY.year, YESTERDAY.month, YESTERDAY.day, 5, 0, tzinfo=UTC
        ),
        actual_arrival=datetime(
            YESTERDAY.year, YESTERDAY.month, YESTERDAY.day, 9, 0, tzinfo=UTC
        ),
    )
    _store(session_factory, "iaa", arriving)

    found = find(session_factory)
    assert found[0].measured_at == "arrival"
    assert found[0].delay == "4.0h"
