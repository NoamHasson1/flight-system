"""Re-run every stored check against today's rules.

    python -m app.tasks.reevaluate --dry-run
    python -m app.tasks.reevaluate

WHAT IT IS FOR
--------------
A verdict is written when the check runs. Improve a rule and every check
already stored keeps the old answer -- including "we could not decide this"
for a flight that now pays.

Reading a result page already re-runs the rules, so a customer who returns
to their link sees the current answer. This is the other half: the customer
who does NOT return. They were told there was nothing, they believed it, and
they are not coming back to look again.

Those people are in the database with an email address. This finds them.

    27 September, two hours apart:
        07:15  WZ4312  NEEDS_REVIEW
        11:19  A45024  LIKELY_ELIGIBLE  ILS1,530

WHY IT WRITES AND THE ENDPOINT DOES NOT
---------------------------------------
Recording a changed verdict is a decision, not a side effect of somebody
opening a page. Done here it happens once, deliberately, with a report of
what moved -- rather than whenever a crawler hits a URL.

IT COSTS NOTHING
----------------
`flight_snapshot` holds the facts each verdict was computed from, so this
is arithmetic over rows we already have. No lookup, no quota, no vendor.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter

from sqlalchemy import select

from app.api.deps import build_engine_and_factory
from app.config import get_settings
from app.db.models import EligibilityCheck
from app.db.repositories import result_detail
from app.services.reevaluate import current_result, has_changed

logger = logging.getLogger("flight_system.reevaluate")


def sweep(session_factory, *, dry_run: bool = False):  # type: ignore[no-untyped-def]
    """Returns (counts, the checks whose answer improved and left an email)."""
    counts: Counter[str] = Counter()
    worth_telling: list[tuple[str, str, str, str]] = []

    with session_factory() as session:
        rows = session.scalars(select(EligibilityCheck)).all()
        for row in rows:
            fresh = current_result(row, session)
            if fresh is None:
                counts["no snapshot to re-run"] += 1
                continue
            if not has_changed(row, fresh):
                counts["unchanged"] += 1
                continue

            before, after = row.verdict, fresh.verdict.value
            counts[f"{before} → {after}"] += 1

            award = fresh.best_award
            # Worth a message only when there is now money and somebody to
            # write to. "Still nothing" is not news, and a changed verdict
            # with no contact address has nobody to tell.
            if award is not None and row.contact_email:
                worth_telling.append(
                    (row.contact_email, row.flight_number, str(row.flight_date),
                     f"{award.amount:,.0f} {award.currency.value}")
                )

            if not dry_run:
                row.verdict = after
                row.best_amount = award.amount if award else None
                row.best_currency = award.currency.value if award else None
                row.best_regulation = fresh.best_regulation
                row.result_detail = result_detail(fresh)
                # The stored message described the old verdict.
                row.message = None

        if not dry_run:
            session.commit()

    return counts, worth_telling


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    _, session_factory = build_engine_and_factory(get_settings())
    counts, worth_telling = sweep(session_factory, dry_run=args.dry_run)

    print()
    print("  would change:" if args.dry_run else "  changed:")
    for label, count in counts.most_common():
        print(f"    {count:6,}  {label}")

    if worth_telling:
        print()
        print(f"  {len(worth_telling)} person(s) were told nothing and are now owed something:")
        for email, number, day, amount in worth_telling:
            print(f"    {email:32} {number:9} {day}   {amount}")
        print()
        print("  Nothing has been sent. Writing to somebody months later")
        print("  saying the answer changed is a decision for a person.")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
