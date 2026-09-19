"""The daily archive: keeping the Ben Gurion board after it forgets.

    python -m app.tasks.archive_board

WHAT THIS IS FOR
----------------
Israel lets a passenger claim for four years. The UK allows six. Every
commercial flight feed we can buy reaches back one year at the very most --
AeroDataBox tops out at 365 days on its $499 plan, and the free Ben Gurion
board publishes a rolling five days before dropping the oldest.

That gap cannot be closed by spending money. There is no subscription that
sells 2023.

It can be closed by paying attention. The board publishes today's truth today;
this job writes it down. Run once a day it never misses a flight, because five
days of window against one day of interval leaves four days of overlap -- so
the machine can be off for most of a week and the archive still has no holes.
Run every day for four years and the archive covers the entire Israeli claim
window, from the authoritative source, owned outright.

It costs nothing and it is worth more every day it is not started.

HOW IT BEHAVES
--------------
Idempotent. Running it twice in an hour changes nothing that matters: each
flight is one row keyed by (provider, number, date), and a row already marked
settled is never overwritten. That last part is what makes the archive
trustworthy -- a flight that has landed cannot be un-landed by a later,
thinner answer from a source that has begun to forget it.

It writes to the same `flight_lookups` table the cache reads. That is not
frugality, it is the same fact: "what did this source say about this flight".
A flight archived last year answers a customer's question this year without a
single API call, and without the board still holding it.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from collections import defaultdict
from collections.abc import Sequence
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import build_engine_and_factory
from app.config import get_settings
from app.db.models import FlightLookup
from app.providers.base import RawFlight
from app.providers.cache import SETTLED, encode, now
from app.providers.iaa import IsraelAirportsProvider

logger = logging.getLogger("flight_system.archive")


async def run() -> int:
    """Take one snapshot and fold it into the archive. Returns rows written."""
    settings = get_settings()
    _, session_factory = build_engine_and_factory(settings)

    provider = IsraelAirportsProvider()
    flights = await provider.snapshot()
    logger.info("board returned %d flights", len(flights))

    written = fold_in(session_factory, provider.name, flights)
    return written


def fold_in(
    session_factory: sessionmaker[Session],
    provider: str,
    flights: Sequence[RawFlight],
) -> int:
    """Write a snapshot into the archive. Returns rows added or updated.

    Separated from `run` so it can be tested without a network, and so a second
    source -- another country's board -- can reuse it unchanged.
    """
    # One row per question a customer could ask, not one per flight: "what flew
    # as LY315 that day" can legitimately be several flights, and the answer is
    # the whole list.
    grouped: dict[tuple[str, date], list[RawFlight]] = defaultdict(list)
    for flight in flights:
        grouped[(flight.flight_number, flight.flight_date)].append(flight)

    written = 0
    kept = 0
    with session_factory() as session:
        for (number, flight_date), group in grouped.items():
            is_final = all(f.status in SETTLED for f in group)
            row = session.scalar(
                select(FlightLookup).where(
                    FlightLookup.provider == provider,
                    FlightLookup.flight_number == number,
                    FlightLookup.flight_date == flight_date,
                )
            )
            if row is None:
                session.add(
                    FlightLookup(
                        provider=provider,
                        flight_number=number,
                        flight_date=flight_date,
                        observed_at=now(),
                        is_final=is_final,
                        flights=[encode(f) for f in group],
                    )
                )
                written += 1
            elif row.is_final:
                # Already settled. Tomorrow's board will not contain today's
                # flight at all, so a run that could overwrite a landed flight
                # with whatever it knows now would leave the archive forever as
                # thin as its most recent snapshot.
                kept += 1
            else:
                row.observed_at = now()
                row.is_final = is_final
                row.flights = [encode(f) for f in group]
                written += 1
        session.commit()

    logger.info(
        "archived %d flight-days (%d new or updated, %d already settled)",
        len(grouped),
        written,
        kept,
    )
    return written


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    try:
        asyncio.run(run())
    except Exception:
        # Logged rather than raised bare, because this runs unattended: a
        # traceback in a cron mail nobody reads is how an archive silently
        # stops being written.
        logger.exception("the archive run failed")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
