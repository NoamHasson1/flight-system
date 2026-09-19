"""Labelling the flights a customer is asked to choose between.

The rule these tests protect is not about correctness of data -- the option
keys were always right -- but about whether a human can act on what is shown.
A screen with two identical buttons is a coin toss wearing a question.

This was found in production data, not in a fixture: BA242 is a daily Mexico
City rotation, so the API returned the 18th's flight and the 19th's, both
leaving at 04:00 UTC. Every hand-written test case happened to use two
different times, which is exactly why none of them caught it.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from app.domain.models import FlightStatus
from app.providers.base import RawFlight
from app.services.eligibility import _build_options


def _record(
    dep: datetime | None, origin: str = "MEX", destination: str = "LHR"
) -> RawFlight:
    return RawFlight(
        flight_number="BA242",
        flight_date=dep.date() if dep else date(2026, 9, 18),
        status=FlightStatus.LANDED,
        provider="test",
        airline_iata="BA",
        origin_iata=origin,
        destination_iata=destination,
        scheduled_departure=dep,
    )


def test_same_clock_time_on_different_days_is_told_apart() -> None:
    """The bug. Two buttons must never read the same."""
    options = _build_options(
        [
            _record(datetime(2026, 9, 18, 4, 0, tzinfo=UTC)),
            _record(datetime(2026, 9, 19, 4, 0, tzinfo=UTC)),
        ]
    )
    labels = [o.label for o in options]
    assert len(set(labels)) == 2, labels
    assert "18 Sep" in labels[0]
    assert "19 Sep" in labels[1]


def test_same_day_keeps_the_label_short() -> None:
    """A date repeated on every button is noise, not information.

    The customer already typed that date into the form; the thing that differs
    is the time, so the time is all that is shown.
    """
    options = _build_options(
        [
            _record(datetime(2026, 8, 14, 7, 25, tzinfo=UTC), "DUB", "STN"),
            _record(datetime(2026, 8, 14, 19, 40, tzinfo=UTC), "DUB", "STN"),
        ]
    )
    labels = [o.label for o in options]
    assert labels == [
        "DUB → STN, departing 07:25 UTC",
        "DUB → STN, departing 19:40 UTC",
    ]


def test_an_unknown_departure_time_says_so() -> None:
    """Some providers return a flight with no scheduled departure at all.

    It still has to be choosable -- and it still must not be confused with a
    flight whose time we do know.
    """
    options = _build_options(
        [
            _record(datetime(2026, 9, 18, 4, 0, tzinfo=UTC)),
            _record(None),
        ]
    )
    labels = [o.label for o in options]
    assert "time unknown" in labels[1]
    assert len(set(labels)) == 2
