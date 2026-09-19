"""Fill in the far end of disrupted flights, while it can still be bought.

    python -m app.tasks.enrich                 # last 7 days
    python -m app.tasks.enrich --min-delay 1   # cast wider
    python -m app.tasks.enrich --dry-run       # what it would cost

WHY THIS EXISTS
---------------
The Ben Gurion board records the movement AT Ben Gurion. A departure row knows
the take-off and never learns the landing; an arrival row knows the landing and
never the take-off. Half of every route's claims turn on the half it does not
have:

    TLV -> Athens, delayed    Israeli law reads the departure   the board has it
                              EC261 reads the arrival           it does not

    Athens -> TLV, delayed    EC261 reads the arrival           the board has it
                              Israeli law reads the departure   it does not

The commercial feed has both ends -- for about a year. After that the flight is
gone from every source that sells it, while the passenger still has years left
to claim. So the far end has to be bought NOW, for the flights that might be
worth something, and kept.

That is the whole job: it is not about answering a question today, it is about
being able to answer one in 2030.

WHAT IT COSTS
-------------
Only disrupted flights, because nobody claims for a punctual one. From a real
week at Ben Gurion that is roughly twenty to forty flights a day at a one-hour
threshold -- a few hundred API units a month against the five thousand a Pro
plan gives.

Flights already complete are skipped, so running it repeatedly costs nothing.
And it never asks twice for the same flight: the answer goes back into the
archive, where the cache finds it.

WHAT IT DELIBERATELY DOES NOT DO
--------------------------------
It does not enrich on-time flights. A flight that left and arrived on schedule
has no claim, and buying its far end is buying the right to answer a question
nobody will ask.

It does not overwrite anything the board said. The board is the airport's own
record, and the commercial feed has been caught mis-dating exactly these
flights. Only empty fields are filled.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.api.deps import build_engine_and_factory
from app.config import get_settings
from app.db.models import FlightLookup
from app.domain.models import FlightStatus
from app.providers.base import FlightDataError, RawFlight
from app.providers.cache import _decode, encode, now
from app.providers.chain import _merge
from app.providers.registry import AERODATABOX, IAA, build_provider

logger = logging.getLogger("flight_system.enrich")

DEFAULT_MIN_DELAY_HOURS = 1.0
DEFAULT_DAYS = 7


def _one_ended(flight: RawFlight) -> bool:
    """True when the record describes only one end of the journey."""
    return flight.scheduled_departure is None or flight.scheduled_arrival is None


def _worth_buying(flight: RawFlight, min_delay_hours: float) -> bool:
    """Whether this flight could plausibly be worth money.

    A cancellation always is. A delay is, once it is long enough that the far
    end might push it over a threshold -- the default is deliberately well
    below any real one, because a flight can leave nearly on time and still
    land hours late, and that is precisely the case the board cannot see.
    """
    if flight.status is FlightStatus.CANCELLED:
        return True
    for scheduled, actual in (
        (flight.scheduled_departure, flight.actual_departure),
        (flight.scheduled_arrival, flight.actual_arrival),
    ):
        if scheduled is not None and actual is not None:
            if (actual - scheduled).total_seconds() / 3600 >= min_delay_hours:
                return True
    return False


async def run(
    *, min_delay_hours: float = DEFAULT_MIN_DELAY_HOURS,
    days: int = DEFAULT_DAYS,
    dry_run: bool = False,
) -> int:
    """Complete what can be completed. Returns the number of flights filled."""
    settings = get_settings()
    _, session_factory = build_engine_and_factory(settings)
    feed = build_provider(AERODATABOX, api_key=settings.aerodatabox_api_key)

    earliest = datetime.now(UTC).date() - timedelta(days=days)

    with session_factory() as session:
        rows = session.scalars(
            select(FlightLookup)
            .where(
                FlightLookup.provider == IAA,
                FlightLookup.flight_date >= earliest,
            )
            .order_by(FlightLookup.flight_date.desc())
        ).all()

        wanted = []
        for row in rows:
            flights = _decode(row.flights, row.provider)
            if not flights:
                continue
            if not any(_one_ended(f) for f in flights):
                continue
            if not any(_worth_buying(f, min_delay_hours) for f in flights):
                continue
            wanted.append((row, flights))

        logger.info(
            "%d archived flight-days, %d disrupted and half-described",
            len(rows), len(wanted),
        )
        if dry_run:
            for row, _ in wanted[:40]:
                logger.info("  would buy %s %s", row.flight_number, row.flight_date)
            logger.info("would spend about %d API units", len(wanted) * 2)
            return 0

        filled = 0
        for row, flights in wanted:
            try:
                other = await feed.fetch(row.flight_number, row.flight_date)
            except FlightDataError as exc:
                # One flight failing must not end the run: the next one may be
                # the cancellation worth ILS3,670, and a rate limit or a single
                # bad record is not a reason to stop buying the rest.
                logger.warning("%s %s: %s", row.flight_number, row.flight_date, exc)
                continue
            if not other:
                continue

            merged = tuple(_merge(f, other) for f in flights)
            if merged == tuple(flights):
                continue

            row.flights = [encode(f) for f in merged]
            row.observed_at = now()
            filled += 1
            logger.info(
                "filled %s %s (%s)",
                row.flight_number, row.flight_date, merged[0].route,
            )
        session.commit()

    logger.info("completed %d flights", filled)
    return filled


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--min-delay", type=float, default=DEFAULT_MIN_DELAY_HOURS,
                        metavar="HOURS")
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS)
    parser.add_argument("--dry-run", action="store_true",
                        help="report what it would buy, and spend nothing")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    try:
        asyncio.run(
            run(min_delay_hours=args.min_delay, days=args.days, dry_run=args.dry_run)
        )
    except Exception:
        logger.exception("the enrichment run failed")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
