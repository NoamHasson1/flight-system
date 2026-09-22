"""Recover a day the archive missed, while it is still for sale.

    python -m app.tasks.backfill --date 2026-09-21 --dry-run
    python -m app.tasks.backfill --from 2026-09-14 --to 2026-09-21

WHAT THIS IS FOR
----------------
The archive is only as complete as the machine running it. A laptop that slept
for forty percent of three days captured forty-two flights of the eight hundred
that used Ben Gurion on 21 September, and the board has long since dropped that
day.

The commercial feed still has it -- for about a year -- and its airport
endpoint returns a whole day at a time. So a day the archive missed can be
bought back, cheaply, as long as somebody does it inside the year.

    2 units per twelve-hour window, 4 per day, about 40 for a fortnight.

That is the whole argument for running this soon rather than eventually: today
it is small change, and in thirteen months it is impossible.

WHY THE AIRPORT ENDPOINT AND NOT ONE CALL PER FLIGHT
----------------------------------------------------
Eight hundred flights at two units each is sixteen hundred units for one day,
against four. The airport endpoint also returns BOTH ends of each journey,
which is what the board can never give and what EC261 needs.

WHAT IT WILL NOT DO
-------------------
Overwrite a settled row. A flight already recorded as landed or cancelled is
not improved by a second opinion, and this runs against days where the local
record may well be the better one.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta

import httpx

from app.api.deps import build_engine_and_factory
from app.config import get_settings
from app.providers.aerodatabox import (
    DEFAULT_BASE_URL,
    DEFAULT_RAPIDAPI_HOST,
    DEFAULT_TIMEOUT,
    _to_raw_flight,
)
from app.providers.base import RawFlight
from app.tasks.archive_board import fold_in

logger = logging.getLogger("flight_system.backfill")

AIRPORT = "TLV"
PROVIDER = "aerodatabox"

# The endpoint accepts at most twelve hours per request, so a day is two.
_WINDOWS = (("00:00", "12:00"), ("12:00", "23:59"))


async def one_day(client: httpx.AsyncClient, key: str, day: date) -> list[RawFlight]:
    """Every movement through Ben Gurion on one date, both ends described."""
    found: list[RawFlight] = []
    for start, end in _WINDOWS:
        url = (
            f"{DEFAULT_BASE_URL}/flights/airports/iata/{AIRPORT}"
            f"/{day.isoformat()}T{start}/{day.isoformat()}T{end}"
        )
        response = await client.get(
            url,
            headers={
                "X-RapidAPI-Key": key,
                "X-RapidAPI-Host": DEFAULT_RAPIDAPI_HOST,
                "Accept": "application/json",
            },
            params={
                "withLeg": "true",  # both ends, which the board never has
                "direction": "Both",
                "withCancelled": "true",  # the rows worth the most
                "withCodeshared": "false",
                "withLocation": "false",
                "withAircraftImage": "false",
            },
        )
        if response.status_code in (204, 404):
            continue
        response.raise_for_status()
        payload = response.json()

        for key_name in ("departures", "arrivals"):
            for item in payload.get(key_name, []) or []:
                number = str(item.get("number") or "").replace(" ", "").upper()
                if not number:
                    continue
                found.append(_to_raw_flight(item, number, day, PROVIDER))
    return found


async def run(
    *, first: date, last: date, dry_run: bool = False
) -> int:
    settings = get_settings()
    if not settings.aerodatabox_api_key.strip():
        logger.error("AERODATABOX_API_KEY is not set; there is nothing to buy from")
        return 0

    _, session_factory = build_engine_and_factory(settings)

    days = []
    cursor = first
    while cursor <= last:
        days.append(cursor)
        cursor += timedelta(days=1)

    logger.info(
        "%s %d day(s), %s to %s, for about %d API units",
        "would buy" if dry_run else "buying",
        len(days), first, last, len(days) * len(_WINDOWS) * 2,
    )
    if dry_run:
        return 0

    written = 0
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        for day in days:
            try:
                flights = await one_day(client, settings.aerodatabox_api_key, day)
            except Exception:
                # One bad day must not end the run: the next might be the one
                # with the cancellation worth ILS3,670.
                logger.exception("could not fetch %s", day)
                continue

            grouped: dict[tuple[str, date], list[RawFlight]] = defaultdict(list)
            for flight in flights:
                grouped[(flight.flight_number, flight.flight_date)].append(flight)

            added = fold_in(
                session_factory, PROVIDER, [f for group in grouped.values() for f in group]
            )
            written += added
            logger.info("%s: %d flights, %d rows written", day, len(flights), added)

    logger.info("backfill complete: %d rows", written)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--date", type=date.fromisoformat, metavar="YYYY-MM-DD")
    parser.add_argument("--from", dest="first", type=date.fromisoformat)
    parser.add_argument("--to", dest="last", type=date.fromisoformat)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if args.date:
        first = last = args.date
    elif args.first and args.last:
        first, last = args.first, args.last
    else:
        parser.error("give --date, or both --from and --to")

    if last < first:
        parser.error("--to is before --from")
    if (datetime.now().date() - first).days > 175:
        logger.warning(
            "%s is close to the feed's 180-day horizon; older days may return "
            "nothing at all",
            first,
        )

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    try:
        asyncio.run(run(first=first, last=last, dry_run=args.dry_run))
    except Exception:
        logger.exception("the backfill failed")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
