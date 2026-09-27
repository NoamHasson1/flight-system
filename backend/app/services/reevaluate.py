"""Answering an old check with today's rules.

THE PROBLEM
-----------
A verdict is written once, when the check runs, and never again. So every
time a rule improves, everybody holding an older result link keeps seeing
the older answer -- including "we could not decide this" for a flight that
now pays.

That is not hypothetical. On 27 September two hours separated these:

    07:15  WZ4312  26-09   NEEDS_REVIEW
    11:19  A45024  26-09   LIKELY_ELIGIBLE   ILS1,530

Same flights, same data, a corrected rule in between. Anyone who checked
before lunch still had a page telling them there was nothing here.

It is the same shape as the archive keeping a stale parse of a raw payload,
which `rederive` fixed. The hole was left open in the other half.

WHY IT COSTS NOTHING TO FIX
---------------------------
`eligibility_checks.flight_snapshot` holds exactly the facts the verdict was
computed from. The model's own docstring has promised this since it was
written: "if a rule turns out to have been wrong, every historical check can
be re-run against the corrected rule without paying for a single lookup
again". The evidence was kept; only the mechanism was missing.

READING DOES NOT WRITE
----------------------
This module only computes. Fetching a result page re-runs the rules and
shows what they now say, and changes nothing in the database -- a GET that
mutates is a GET that cannot be retried, cached, or run twice safely, and
two tabs open on the same claim would race each other.

Recording the change is a deliberate act, done by `app.tasks.reevaluate`,
which reports what moved and can tell the people affected.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import EligibilityCheck
from app.providers.cache import SETTLED as _SETTLED
from app.domain.models import FlightFacts, FlightStatus
from app.domain.rules import engine
from app.domain.rules.engine import EligibilityResult


def facts_from_snapshot(snapshot: dict[str, Any] | None) -> FlightFacts | None:
    """Rebuild the facts a verdict was computed from.

    Returns None rather than raising on anything unexpected. A snapshot
    written by an older version of this code may be missing a field, and a
    result page must still render -- showing the stored verdict is a far
    better failure than a 500.
    """
    if not snapshot:
        return None
    try:
        return FlightFacts(
            flight_number=snapshot["flight_number"],
            flight_date=_date(snapshot["flight_date"]),
            airline_iata=snapshot["airline_iata"],
            airline_country=snapshot["airline_country"],
            origin_iata=snapshot["origin_iata"],
            origin_country=snapshot["origin_country"],
            destination_iata=snapshot["destination_iata"],
            destination_country=snapshot["destination_country"],
            distance_km=float(snapshot["distance_km"]),
            scheduled_departure=_time(snapshot.get("scheduled_departure")),
            scheduled_arrival=_time(snapshot.get("scheduled_arrival")),
            actual_departure=_time(snapshot.get("actual_departure")),
            actual_arrival=_time(snapshot.get("actual_arrival")),
            status=FlightStatus(snapshot["status"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def facts_from_archive(check: EligibilityCheck, session: Session) -> FlightFacts | None:
    """The same flight, read out of the archive with today's parser.

    WHY THE SNAPSHOT IS NOT ENOUGH.

    The snapshot froze what we UNDERSTOOD at the time, not what the source
    said. A45024 was captured while the parser discarded the board's revised
    departure time, so its snapshot has no departure time -- and re-running
    the rules over it returns NEEDS_REVIEW forever, correctly, because the
    facts it holds really are insufficient.

    The archive keeps the raw payload, and `rederive` has since re-read it.
    So the better record is sitting in `flight_lookups`, and using it costs
    nothing: no lookup, no quota, no vendor. Only data we already own.

    Never fetches. A check that cannot be improved from what we hold is left
    exactly as it is.
    """
    from app.db.models import FlightLookup
    from app.providers.cache import _decode
    from app.providers.mapper import MappingFailure, to_flight_facts

    rows = session.scalars(
        select(FlightLookup).where(
            FlightLookup.flight_number == check.flight_number,
            FlightLookup.flight_date == check.flight_date,
        )
    ).all()

    best: FlightFacts | None = None
    for row in rows:
        for flight in _decode(row.flights, row.provider):
            facts = to_flight_facts(flight)
            if isinstance(facts, MappingFailure):
                continue
            if best is None or _confidence(facts) > _confidence(best):
                best = facts
    return best


def _confidence(facts: FlightFacts) -> tuple[int, int]:
    """How much a record KNOWS. Bigger is better; ties go to the incumbent.

    Two parts, in order:

      1. Is the status settled? LANDED, CANCELLED and DIVERTED are things
         that happened. SCHEDULED and EN_ROUTE are things expected to
         happen, and a prediction must never displace a fact.
      2. How many of the four times it has.

    Every wrong choice this function exists to prevent was found by running
    the sweep against real rows and reading the three that moved DOWN:

      BZ611   snapshot CANCELLED, no times · archive EN_ROUTE, four times
              -- more times, but "en route" is the board guessing, and the
              cancellation is why the passenger has a claim. Part 1.

      A45024  snapshot has the revised departure, archive row does not
              -- the archive is not uniformly richer, and preferring it
              would have discarded the exact fix that prompted all this.
              Part 2.

      IZ162   identical times, CANCELLED against LANDED
              -- two sources disagreeing, no new information either way.
              A tie, so nothing moves.
    """
    settled = facts.status in _SETTLED
    times = sum(
        1
        for value in (
            facts.scheduled_departure,
            facts.actual_departure,
            facts.scheduled_arrival,
            facts.actual_arrival,
        )
        if value is not None
    )
    return (1 if settled else 0, times)


def current_result(
    check: EligibilityCheck, session: Session | None = None
) -> EligibilityResult | None:
    """What the rules say about this check TODAY, or None if they cannot say.

    With a session, the archive is consulted first -- it may hold a better
    reading of the same flight than the snapshot froze. Without one, the
    snapshot is used, which is right for a read path that must not run
    extra queries on every page view.
    """
    facts = facts_from_snapshot(check.flight_snapshot)
    if session is not None:
        archived = facts_from_archive(check, session)
        # Strictly better, never merely different. A tie keeps the snapshot:
        # it is what the passenger was actually shown, and churning a verdict
        # because two equally-informed records disagree is noise.
        if archived is not None and (
            facts is None or _confidence(archived) > _confidence(facts)
        ):
            facts = archived
    if facts is None:
        return None
    return engine.evaluate(facts)


def has_changed(check: EligibilityCheck, result: EligibilityResult) -> bool:
    """Whether today's rules disagree with what this check was told.

    Compares the verdict AND the amount. A verdict that stayed ELIGIBLE while
    the award went from EUR250 to ILS1,530 has changed in the only way the
    customer cares about.
    """
    award = result.best_award
    # Compared as formatted strings, not as numbers: `best_amount` is a
    # Decimal from the database and an award's is a Decimal from the rules,
    # and two Decimals that print the same can still differ in scale.
    amount = f"{award.amount:.2f}" if award else None
    stored = f"{check.best_amount:.2f}" if check.best_amount is not None else None
    return check.verdict != result.verdict.value or stored != amount


def _date(value: Any):  # type: ignore[no-untyped-def]
    from datetime import date

    return value if isinstance(value, date) else date.fromisoformat(str(value))


def _time(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))
