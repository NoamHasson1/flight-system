"""Re-read the archive's raw payloads with today's parser.

    python -m app.tasks.rederive --dry-run
    python -m app.tasks.rederive

THE PROBLEM
-----------
`flight_lookups` stores two things per flight: the source's RAW payload, and
the fields we derived from it. Derived fields are written once, at capture.

So when the parser improves, the archive does not. A row captured on Monday
keeps Monday's understanding of it forever, and the board has usually shed
that day by the time anybody notices -- at which point the row cannot be
refetched and the improvement can never reach it.

That is how a fix becomes temporary. The declared-delay fix on 27 September
corrected A45024 only because the board still held the day and a refetch
happened to run. Fifteen other flights the board had explicitly marked
DELAYED kept their empty departure time, and would have kept it for four
years -- each one a real claim answered "we need to check this by hand".

WHY IT IS FIXABLE AT ALL
------------------------
Because the raw payload is kept. Every derived field can be computed again
from what the source actually said, locally, with no API call and no quota.
That is the whole reason for storing `raw` alongside, and this is the task
that cashes it in.

WHAT IT WILL NOT DO
-------------------
Invent anything. It re-runs the same adapter a live fetch would run, over
bytes the source already gave us. If the new parser produces the same values
the row is left alone, so this is safe to run as often as you like and after
every parser change.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter

from sqlalchemy import select

from app.api.deps import build_engine_and_factory
from app.config import get_settings
from app.db.models import FlightLookup
from app.providers.cache import _decode, encode
from app.providers.iaa import _to_raw_flight as iaa_parse

logger = logging.getLogger("flight_system.rederive")

# Only sources whose raw payload we can re-parse. AeroDataBox records are
# stored raw too, but its adapter shapes a record from a nested response
# rather than a flat row, so re-deriving it needs the original envelope --
# which is not what we keep. The board is the one that matters here anyway:
# it is the source we archive in full.
PARSERS = {"iaa": iaa_parse}


def rederive(session_factory, *, dry_run: bool = False) -> Counter[str]:  # type: ignore[no-untyped-def]
    """Recompute every derived field from the stored raw payload."""
    counts: Counter[str] = Counter()

    with session_factory() as session:
        rows = session.scalars(select(FlightLookup)).all()
        for row in rows:
            parse = PARSERS.get(row.provider)
            if parse is None:
                counts["skipped (no parser for this source)"] += 1
                continue

            stored = _decode(row.flights, row.provider)
            if not stored:
                counts["skipped (empty row)"] += 1
                continue

            rebuilt = []
            for flight in stored:
                raw = flight.raw
                if not raw:
                    # Nothing to re-read. Keep what we have rather than
                    # replacing a real record with a guess.
                    rebuilt.append(flight)
                    continue
                rebuilt.append(
                    parse(raw, row.flight_number, row.flight_date, row.provider)
                )

            before = [encode(f) for f in stored]
            after = [encode(f) for f in rebuilt]
            if before == after:
                counts["unchanged"] += 1
                continue

            counts["updated"] += 1
            gained = sum(
                1
                for b, a in zip(before, after, strict=True)
                if b.get("actual_departure") is None
                and a.get("actual_departure") is not None
            )
            if gained:
                counts["gained a departure time"] += gained
            if not dry_run:
                row.flights = after

        if not dry_run:
            session.commit()

    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    _, session_factory = build_engine_and_factory(get_settings())
    counts = rederive(session_factory, dry_run=args.dry_run)

    print()
    print("  would re-derive:" if args.dry_run else "  re-derived:")
    for label, count in counts.most_common():
        print(f"    {count:6,}  {label}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
