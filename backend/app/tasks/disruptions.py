"""Every disrupted flight in the archive, with what we would pay for it.

    python -m app.tasks.disruptions                  # last 7 days, 3h+
    python -m app.tasks.disruptions --min-delay 8    # only the Israeli threshold
    python -m app.tasks.disruptions --days 30 --csv disruptions.csv

WHAT THIS IS
------------
A report, not a second store. The archive already holds every flight the board
published; a disruption is a query over it, and keeping a separate table of
"the interesting ones" would be a copy that drifts from the thing it copies.

WHY IT IS WORTH HAVING
----------------------
Two uses, and the second is the one that pays.

Checking our answers. Run the same flights through another service and the
differences are either a bug of ours or a bug of theirs, and either is worth
knowing before a customer finds it. Comparing a verdict at a time is slow;
comparing a table is not.

Finding the customers. Every row here is a passenger who is owed money and
does not know it. A cancelled Tel Aviv to Heraklion flight is a hundred and
eighty people with a claim, and this is the list of them -- which is a very
different business from waiting for someone to type a flight number.

WHAT IT CANNOT TELL YOU
-----------------------
Only what the archive saw. A flight that came and went between two runs of
`archive_board` is not here, because it was never captured -- which is the
argument for running that job every few minutes rather than nightly.

And the board records only the Ben Gurion end of a journey. An arrival knows
when it landed and not when it left, so a flight INTO Israel usually cannot be
judged under Israeli law from this alone, and shows as needing review. That is
the honest state of the data, not a failure of the report.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections.abc import Iterator
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select

from app.api.deps import build_engine_and_factory
from app.config import get_settings
from app.db.models import FlightLookup
from app.domain.models import FlightFacts, FlightStatus, Verdict
from app.providers.base import RawFlight
from app.providers.cache import _decode
from app.providers.mapper import MappingFailure, to_flight_facts
from app.domain.rules import engine

DEFAULT_MIN_DELAY_HOURS = 3.0
DEFAULT_DAYS = 7


@dataclass(frozen=True, slots=True)
class Disruption:
    """One disrupted flight, and what the rules make of it."""

    flight_date: date
    flight_number: str
    route: str
    status: str
    delay_hours: float | None
    measured_at: str  # "departure" or "arrival" -- the board knows one end
    verdict: str
    amount: str
    regulation: str
    source: str

    @property
    def delay(self) -> str:
        if self.delay_hours is None:
            return "—"
        return f"{self.delay_hours:.1f}h"


def find(
    session_factory,  # type: ignore[no-untyped-def]
    *,
    min_delay_hours: float = DEFAULT_MIN_DELAY_HOURS,
    days: int = DEFAULT_DAYS,
) -> list[Disruption]:
    """Every cancellation, and every delay at or over the threshold."""
    earliest = datetime.now(UTC).date() - timedelta(days=days)
    found: list[Disruption] = []

    with session_factory() as session:
        rows = session.scalars(
            select(FlightLookup)
            .where(FlightLookup.flight_date >= earliest)
            .order_by(FlightLookup.flight_date.desc())
        ).all()

        for row in rows:
            for flight in _decode(row.flights, row.provider):
                delay, measured = _delay(flight)
                cancelled = flight.status is FlightStatus.CANCELLED
                if not cancelled and (delay is None or delay < min_delay_hours):
                    continue
                found.append(
                    _describe(row, flight, delay, measured)
                )

    found = _one_row_per_flight(found)

    # Worst first: a cancellation outranks any delay, then the longest delay.
    # Someone reading this top-down is reading it in order of what is owed.
    found.sort(
        key=lambda d: (
            d.status != "CANCELLED",
            -(d.delay_hours or 0.0),
        )
    )
    return found


# How good an answer is, for choosing between two sources that both have the
# flight. A decision beats a question; a definite decision beats a provisional
# one. NOT_ELIGIBLE ranks last on purpose: when one source can price a flight
# and another cannot see far enough to judge it, the priced answer is the one
# with more information behind it, and the cheapest mistake here is the one
# that shows a claim to someone who turns out not to have one.
_ANSWER_RANK = {
    Verdict.ELIGIBLE.value: 0,
    Verdict.LIKELY_ELIGIBLE.value: 1,
    Verdict.NEEDS_REVIEW.value: 2,
    Verdict.NOT_ELIGIBLE.value: 3,
}


def _one_row_per_flight(found: list[Disruption]) -> list[Disruption]:
    """Collapse the sources, and say when they disagreed.

    Both sources hold most Tel Aviv flights, and listing each twice makes a
    comparison table twice as long and half as readable. The better-informed
    answer is kept -- usually the one that could see both ends of the journey.

    A disagreement is not hidden, though. Two sources reaching different
    verdicts about the same flight is the single most useful thing this report
    can surface: it is either a data problem worth chasing or a bug worth
    fixing, and both are cheaper to find here than in front of a customer.
    """
    by_flight: dict[tuple[date, str], list[Disruption]] = {}
    for d in found:
        by_flight.setdefault((d.flight_date, d.flight_number), []).append(d)

    collapsed: list[Disruption] = []
    for group in by_flight.values():
        group.sort(key=lambda d: (_ANSWER_RANK.get(d.verdict, 9), not d.amount))
        best = group[0]
        others = {d.verdict for d in group[1:]}
        if others - {best.verdict}:
            disagreed = ", ".join(
                f"{d.source}:{d.verdict}" for d in group[1:]
                if d.verdict != best.verdict
            )
            best = replace(best, source=f"{best.source} (≠ {disagreed})")
        collapsed.append(best)
    return collapsed


def _delay(flight: RawFlight) -> tuple[float | None, str]:
    """The delay we can actually measure, and which end it was measured at.

    Computed from the raw record rather than from FlightFacts, because this
    report has to describe flights the mapper rejects -- an unknown airport, a
    missing half -- and those are exactly the rows worth looking at.

    A departure row from the board knows the take-off and nothing else; an
    arrival row knows the landing. Saying which is not decoration: Israeli law
    reads the first and EC261 reads the second, so anyone comparing against
    another service needs to know which number they are looking at.
    """
    for scheduled, actual, where in (
        (flight.scheduled_departure, flight.actual_departure, "departure"),
        (flight.scheduled_arrival, flight.actual_arrival, "arrival"),
    ):
        if scheduled is not None and actual is not None:
            return (actual - scheduled).total_seconds() / 3600, where
    return None, "—"


def _describe(row: FlightLookup, raw, delay, measured) -> Disruption:  # type: ignore[no-untyped-def]
    facts = to_flight_facts(raw)
    if isinstance(facts, MappingFailure):
        return Disruption(
            flight_date=row.flight_date,
            flight_number=row.flight_number,
            route=raw.route,
            status=raw.status.value,
            delay_hours=delay,
            measured_at=measured,
            verdict="NEEDS_REVIEW",
            amount="",
            regulation="",
            source=row.provider,
        )

    result = engine.evaluate(facts)
    return Disruption(
        flight_date=row.flight_date,
        flight_number=row.flight_number,
        route=facts.route,
        status=facts.status.value,
        delay_hours=delay,
        measured_at=measured,
        verdict=result.verdict.value,
        amount=str(result.best_award) if result.best_award else "",
        regulation=result.best_regulation or "",
        source=row.provider,
    )


# --- Output ------------------------------------------------------------------


def _rows(found: list[Disruption]) -> Iterator[list[str]]:
    yield ["date", "flight", "route", "status", "delay", "measured", "verdict",
           "amount", "law", "source"]
    for d in found:
        yield [
            d.flight_date.isoformat(), d.flight_number, d.route, d.status,
            d.delay, d.measured_at, d.verdict, d.amount, d.regulation, d.source,
        ]


def _print(found: list[Disruption], min_delay_hours: float, days: int) -> None:
    if not found:
        print(
            f"No disruptions in the archive for the last {days} days at "
            f"{min_delay_hours:g}h or more.\n"
            f"If that seems wrong, the archive may simply not have been "
            f"running: python -m app.tasks.archive_board"
        )
        return

    table = list(_rows(found))
    widths = [max(len(r[i]) for r in table) for i in range(len(table[0]))]
    header, *body = table
    print("  ".join(h.upper().ljust(w) for h, w in zip(header, widths)))
    print("  ".join("-" * w for w in widths))
    for line in body:
        print("  ".join(c.ljust(w) for c, w in zip(line, widths)))

    payable = [d for d in found
               if d.verdict in (Verdict.ELIGIBLE.value, Verdict.LIKELY_ELIGIBLE.value)]
    print(
        f"\n{len(found)} disrupted flights · {len(payable)} with a claim · "
        f"{len(found) - len(payable)} needing a person or not owed"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--min-delay", type=float, default=DEFAULT_MIN_DELAY_HOURS,
                        metavar="HOURS", help="ignore delays shorter than this")
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS,
                        help="how far back to look")
    parser.add_argument("--csv", metavar="PATH", help="also write the table here")
    args = parser.parse_args(argv)

    _, session_factory = build_engine_and_factory(get_settings())
    found = find(session_factory, min_delay_hours=args.min_delay, days=args.days)
    _print(found, args.min_delay, args.days)

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as handle:
            csv.writer(handle).writerows(_rows(found))
        print(f"written to {args.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
