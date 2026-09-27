"""Everything the system refuses to answer, and why -- ranked.

    python -m app.tasks.refusals
    python -m app.tasks.refusals --days 30 --examples 5

THE PROBLEM THIS EXISTS TO SOLVE
--------------------------------
Four separate bugs were found in one week, all the same shape: a guard that
discards information, written for a good reason, never measured.

    a codeshare arrival carrying a name and no code   -> refused
    an unsettled row for a day the board has shed     -> refused
    two records of one flight, same key               -> asked forever
    a delay the airport declared in writing           -> discarded

Each was defensible alone. Together they were silently refusing real claims,
and every one was found the same way: a person tried a flight, noticed the
answer was wrong, and said so. That is not a detection mechanism. It finds
the flights somebody happens to check and misses the rest, and the rest is
where the money is.

The root cause is not any one guard. It is that THE SYSTEM HAS NO FEEDBACK ON
ITS OWN REFUSALS. It produces NEEDS_REVIEW and "not found" into the void, and
nobody has ever seen the totals.

WHAT THIS DOES
--------------
Runs every flight in the archive through the same mapper and the same rules a
customer's check uses, and counts what comes out. Not to decide anything --
to make the refusals visible and ranked, so the one being hit nine hundred
times gets fixed before the one being hit twice.

It is deliberately the WHOLE pipeline rather than a unit test of each guard.
A guard that is correct in isolation and wrong in aggregate is exactly the
failure mode here, and only running real data through all of it shows that.

WHAT A HEALTHY REPORT LOOKS LIKE
--------------------------------
Refusals never reach zero and should not. A flight still in the air has no
arrival; a diverted one genuinely needs a person. What matters is the SHAPE:
a reason that suddenly climbs, or one that was always large and nobody
noticed, is a bug with a queue of real claims behind it.
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select

from app.api.deps import build_engine_and_factory
from app.config import get_settings
from app.db.models import FlightLookup
from app.domain.models import Verdict
from app.domain.rules import engine
from app.providers.cache import _decode
from app.providers.mapper import MappingFailure, to_flight_facts

logger = logging.getLogger("flight_system.refusals")

DEFAULT_DAYS = 14

# Reasons name the flight that produced them -- "we do not recognise the
# airline BZ", "we do not recognise the destination airport HER". Grouping on
# the raw text would give one bucket per airline and hide the pattern, which
# is the whole point of counting. So codes and numbers are replaced by a
# placeholder and the SHAPE is what gets counted.
_SPECIFIC = re.compile(r"\b[A-Z0-9]{2,4}\d*\b")


def _shape(reason: str) -> str:
    return _SPECIFIC.sub("…", reason).strip()


def survey(
    session_factory,  # type: ignore[no-untyped-def]
    *,
    days: int = DEFAULT_DAYS,
) -> tuple[Counter[str], dict[str, list[str]], Counter[str]]:
    """(reasons refused, examples per reason, verdicts reached)."""
    earliest = datetime.now(UTC).date() - timedelta(days=days)
    refused: Counter[str] = Counter()
    examples: dict[str, list[str]] = defaultdict(list)
    verdicts: Counter[str] = Counter()

    with session_factory() as session:
        rows = session.scalars(
            select(FlightLookup).where(FlightLookup.flight_date >= earliest)
        ).all()

        for row in rows:
            flights = _decode(row.flights, row.provider)
            if not flights:
                refused["the archive holds an empty answer for this flight"] += 1
                examples["the archive holds an empty answer for this flight"].append(
                    f"{row.flight_number} {row.flight_date} [{row.provider}]"
                )
                continue

            for flight in flights:
                where = f"{row.flight_number} {row.flight_date} [{row.provider}]"
                facts = to_flight_facts(flight)
                if isinstance(facts, MappingFailure):
                    for problem in facts.problems:
                        key = _shape(problem)
                        refused[key] += 1
                        if len(examples[key]) < 10:
                            examples[key].append(where)
                    continue

                result = engine.evaluate(facts)
                verdicts[result.verdict.value] += 1
                if result.verdict is Verdict.NEEDS_REVIEW:
                    # A verdict, but not an answer. The reason belongs in the
                    # same ranking as a mapping failure -- from a customer's
                    # side they are the same disappointment.
                    for outcome in result.outcomes:
                        if outcome.verdict is Verdict.NEEDS_REVIEW and outcome.applies:
                            key = _shape(outcome.reason)
                            refused[key] += 1
                            if len(examples[key]) < 10:
                                examples[key].append(where)

    return refused, examples, verdicts


def report(
    refused: Counter[str], examples: dict[str, list[str]], verdicts: Counter[str],
    *, show: int
) -> str:
    total_decided = sum(verdicts.values())
    total_refused = sum(refused.values())
    lines = [
        "",
        f"  {total_decided:,} flights reached a verdict",
        f"  {total_refused:,} refusals to count",
        "",
        "  verdicts reached:",
    ]
    for verdict, count in verdicts.most_common():
        lines.append(f"    {count:6,}  {verdict}")

    lines += ["", "  refused, worst first:"]
    for reason, count in refused.most_common():
        share = count / total_refused * 100 if total_refused else 0
        lines.append(f"    {count:6,}  ({share:4.1f}%)  {reason}")
        for example in examples[reason][:show]:
            lines.append(f"              e.g. {example}")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS)
    parser.add_argument(
        "--examples", type=int, default=2,
        help="flights to name under each reason, so it can be chased",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.WARNING)
    _, session_factory = build_engine_and_factory(get_settings())
    refused, examples, verdicts = survey(session_factory, days=args.days)
    print(report(refused, examples, verdicts, show=args.examples))
    return 0


if __name__ == "__main__":
    sys.exit(main())
