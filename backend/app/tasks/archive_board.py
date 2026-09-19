"""The daily archive: keeping the Ben Gurion board after it forgets.

    python -m app.tasks.archive_board

WHAT THIS IS FOR
----------------
Israel lets a passenger claim for four years. The UK allows six. Every
commercial flight feed we can buy reaches back one year at the very most --
AeroDataBox tops out at 365 days on its $499 plan -- and the Ben Gurion board
does not reach back at all.

That gap cannot be closed by spending money. There is no subscription that
sells 2023.

It can be closed by paying attention. The board publishes today's truth today;
this job writes it down.

HOW OFTEN
---------
Every few minutes, not once a night.

The board is not a five-day window over a fixed set of days. It SHEDS THE PAST
CONTINUOUSLY: 189 flights were recorded for one day at 09:00 and only 145 of
them were still listed four hours later. A flight can be added, cancelled and
dropped between two nightly runs, and a cancellation is the most valuable row
there is.

That is a real, measured miss. IZ1168 on 18 September was cancelled and paid
ILS1,530; it was on the board on the 17th and gone by the 19th, so a daily job
would never have seen it.

Running often is free -- no key, no quota, one request -- and an unchanged row
is skipped rather than rewritten, so a run that finds nothing new costs a
single HTTP call and a few hundred reads.

    */15 * * * *  cd /path/to/backend && uv run python -m app.tasks.archive_board

HOW IT BEHAVES
--------------
Idempotent. Running it twice in a minute changes nothing: each flight is one
row keyed by (provider, number, date), a row already marked settled is never
overwritten, and a row whose contents have not changed is left alone. That
middle part is what makes the archive trustworthy -- a flight that has landed
cannot be un-landed by a later, thinner answer from a source that has begun to
forget it.

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
            payload = [encode(f) for f in group]
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
                        flights=payload,
                    )
                )
                written += 1
            elif row.is_final or row.flights == payload:
                # Already settled, or unchanged since the last run.
                #
                # Settled rows are never rewritten: tomorrow's board will not
                # contain today's flight at all, so a run that could overwrite a
                # landed flight with whatever it knows now would leave the
                # archive forever as thin as its most recent snapshot.
                #
                # Unchanged rows are skipped so that running this every few
                # minutes costs almost nothing. That matters more than it
                # sounds: the board sheds the past continuously -- 44 of the
                # 189 flights recorded for one day had vanished from it four
                # hours later -- so a daily job misses everything that appears
                # and disappears in between, which includes cancellations.
                kept += 1
            else:
                row.observed_at = now()
                row.is_final = is_final
                row.flights = payload
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
