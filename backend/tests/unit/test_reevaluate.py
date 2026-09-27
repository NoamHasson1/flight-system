"""Re-running an old check against today's rules.

WHY THESE TESTS AND NOT OTHERS

Every case below is a mistake that was actually made, not a branch that
happened to need covering. The module has three jobs -- rebuild the facts,
choose between two records of the same flight, and decide whether anything
moved -- and the middle one is where the real danger is: a re-evaluation
that picks the WRONG record silently converts a customer's "you are owed
1,530 shekels" into "you are owed nothing", using data we already had.

So the bulk of this file is the choice. The first version of it preferred
the archive unconditionally, and a dry run over 118 real checks moved three
of them DOWN. Those three are now tests.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal

from app.domain.models import FlightStatus
from app.services.reevaluate import (
    _confidence,
    facts_from_snapshot,
    has_changed,
)
from tests.unit.builders import a_flight


# --- rebuilding the facts ----------------------------------------------------


def test_a_snapshot_round_trips_into_the_facts_it_came_from() -> None:
    """The base case, and the one the whole module rests on.

    `flight_snapshot` is written by the check and read back here, possibly
    months later by different code. If the two ever disagree about a field
    name, every re-evaluation silently returns None and the feature quietly
    does nothing at all -- no error, no log, just a sweep that always
    reports "unchanged".
    """
    original = a_flight(arrival_delay_hours=4.0)
    snapshot = {
        "flight_number": original.flight_number,
        "flight_date": original.flight_date.isoformat(),
        "airline_iata": original.airline_iata,
        "airline_country": original.airline_country,
        "origin_iata": original.origin_iata,
        "origin_country": original.origin_country,
        "destination_iata": original.destination_iata,
        "destination_country": original.destination_country,
        "distance_km": original.distance_km,
        "scheduled_departure": original.scheduled_departure.isoformat(),
        "scheduled_arrival": original.scheduled_arrival.isoformat(),
        "actual_departure": original.actual_departure.isoformat(),
        "actual_arrival": original.actual_arrival.isoformat(),
        "status": original.status.value,
    }

    assert facts_from_snapshot(snapshot) == original


def test_a_snapshot_missing_a_field_returns_none_rather_than_raising() -> None:
    """An old row must not be able to 500 a result page.

    Snapshots outlive the code that wrote them -- that is the entire point
    of keeping them. A field added to FlightFacts next year is a field
    absent from every row written this year, and the right answer then is
    "the rules cannot speak to this one", which shows the customer the
    verdict they were originally given.
    """
    assert facts_from_snapshot({"flight_number": "XX100"}) is None


def test_no_snapshot_at_all_returns_none() -> None:
    """NOT_FOUND and failed lookups are stored as checks with no flight.

    They are a third of the table. Re-evaluating them is not a failure to
    report, it is nothing to do.
    """
    assert facts_from_snapshot(None) is None
    assert facts_from_snapshot({}) is None


# --- choosing between two records of the same flight -------------------------
#
# Each of these is one row from the dry run of 27 September that moved the
# wrong way.


def test_a_cancellation_beats_a_fuller_record_that_is_only_a_prediction() -> None:
    """BZ611, 23 September. The most expensive mistake available here.

    The snapshot said CANCELLED and carried a single time. The archive row
    said EN_ROUTE and carried all four. Preferring the fuller record moved
    the check from LIKELY_ELIGIBLE to NOT_ELIGIBLE -- because a 40-minute
    departure delay pays nothing, while the cancellation that actually
    happened pays EUR400.

    A settled status is a thing that happened. EN_ROUTE is the board saying
    what it expects. More fields is not more knowledge when the extra
    fields describe a flight that was called off.
    """
    cancelled = replace(
        a_flight(arrival_delay_hours=None, departure_delay_hours=None),
        status=FlightStatus.CANCELLED,
    )
    en_route = replace(
        a_flight(arrival_delay_hours=0.7),
        status=FlightStatus.EN_ROUTE,
    )

    assert _confidence(cancelled) > _confidence(en_route)


def test_between_two_unsettled_records_the_one_with_more_times_wins() -> None:
    """A45024, 26 September -- the flight this whole feature was built for.

    Both records are SCHEDULED, because the board never marked the flight
    landed before it shed the day. The snapshot has the revised departure
    (17 hours late, which is why it pays); the archive row does not.

    The first version preferred the archive whenever it existed, which
    would have thrown away the exact correction that prompted all of this.
    """
    with_revision = a_flight(departure_delay_hours=17.0, arrival_delay_hours=None)
    without = a_flight(departure_delay_hours=None, arrival_delay_hours=None)
    with_revision = replace(with_revision, status=FlightStatus.SCHEDULED)
    without = replace(without, status=FlightStatus.SCHEDULED)

    assert _confidence(with_revision) > _confidence(without)


def test_two_equally_informed_records_tie_and_nothing_moves() -> None:
    """IZ162, 25 September. Two sources disagreeing is not new information.

    Identical times; one source said CANCELLED and the other LANDED. There
    is no basis in the data for preferring either, and `current_result`
    only replaces the snapshot on a STRICTLY greater confidence -- so a tie
    leaves the customer seeing what they were originally told, instead of
    the verdict flipping according to which row the query returned first.
    """
    cancelled = replace(a_flight(arrival_delay_hours=2.0), status=FlightStatus.CANCELLED)
    landed = replace(a_flight(arrival_delay_hours=2.0), status=FlightStatus.LANDED)

    assert _confidence(cancelled) == _confidence(landed)


def test_a_settled_status_outranks_any_number_of_times() -> None:
    """The ordering inside the tuple, stated directly.

    Written because the two parts are compared lexicographically and that
    is easy to get backwards in a refactor: swapping them would restore the
    BZ611 bug while every other test in this file still passed.
    """
    settled_and_bare = replace(
        a_flight(arrival_delay_hours=None, departure_delay_hours=None),
        status=FlightStatus.LANDED,
        scheduled_departure=None,
        scheduled_arrival=None,
    )
    unsettled_and_full = replace(
        a_flight(arrival_delay_hours=3.0), status=FlightStatus.SCHEDULED
    )

    assert _confidence(settled_and_bare) > _confidence(unsettled_and_full)


# --- deciding whether anything moved -----------------------------------------


class _Check:
    """Only the three fields `has_changed` reads."""

    def __init__(self, verdict: str | None, amount: Decimal | None) -> None:
        self.verdict = verdict
        self.best_amount = amount


class _Award:
    def __init__(self, amount: Decimal) -> None:
        self.amount = amount


class _Result:
    def __init__(self, verdict: str, amount: Decimal | None) -> None:
        self.verdict = type("V", (), {"value": verdict})()
        self.best_award = _Award(amount) if amount is not None else None


def test_the_same_verdict_for_a_different_amount_counts_as_changed() -> None:
    """The case a verdict-only comparison misses entirely.

    A check can stay LIKELY_ELIGIBLE while the award moves from EUR250 to
    ILS1,530 -- which happened when the Israeli rule started applying to
    flights it had been skipping. The verdict is the same word; the
    customer is owed six times as much. Comparing only the verdict would
    report that as "unchanged" and never tell them.
    """
    stored = _Check("LIKELY_ELIGIBLE", Decimal("250.00"))
    fresh = _Result("LIKELY_ELIGIBLE", Decimal("1530.00"))

    assert has_changed(stored, fresh) is True  # type: ignore[arg-type]


def test_the_same_amount_written_at_a_different_scale_is_not_a_change() -> None:
    """Decimal("1530.00") and Decimal("1530") are not equal, and must be here.

    The database returns a Decimal whose scale comes from the column; the
    rules produce one whose scale comes from arithmetic. Comparing them
    directly makes every sweep report every row as changed, which would
    turn the notification list into noise on its first run.
    """
    stored = _Check("ELIGIBLE", Decimal("1530"))
    fresh = _Result("ELIGIBLE", Decimal("1530.00"))

    assert has_changed(stored, fresh) is False  # type: ignore[arg-type]


def test_a_check_that_found_nothing_gaining_an_award_is_a_change() -> None:
    """The HM9349 shape: verdict None, amount None, now worth ILS3,670.

    Twelve rows in production are this. They were told we could not
    identify the flight; the archive has held it all along.
    """
    stored = _Check(None, None)
    fresh = _Result("LIKELY_ELIGIBLE", Decimal("3670.00"))

    assert has_changed(stored, fresh) is True  # type: ignore[arg-type]


def test_nothing_moving_reports_nothing() -> None:
    """The overwhelmingly common case, and the one that must stay quiet.

    A sweep that reports healthy rows as changed is a sweep nobody reads.
    """
    stored = _Check("NOT_ELIGIBLE", None)
    fresh = _Result("NOT_ELIGIBLE", None)

    assert has_changed(stored, fresh) is False  # type: ignore[arg-type]


# Kept honest: the builders default to 14 August 2026, and these tests assert
# on relationships rather than on dates, so a change of default cannot make
# them pass for the wrong reason.
assert a_flight().flight_date == date(2026, 8, 14)
assert a_flight().scheduled_departure == datetime(2026, 8, 14, 10, 0, tzinfo=UTC)
