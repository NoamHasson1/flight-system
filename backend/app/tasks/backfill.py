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

# THE PLAN HAS A PER-SECOND LIMIT, AND THIS LOOP IS THE ONE THING THAT HITS IT.
#
# Every other caller asks about one flight because a customer is waiting. This
# asks for a fortnight as fast as the network allows, so it is the only place
# that ever meets the throttle -- and it met it on the first real run, dying
# with a bare 429 after two days of eight.
#
# A pause between requests is the whole fix. Slower than necessary on a good
# day and correct on every day, which is the right trade for a job nobody
# watches.
_PAUSE_SECONDS = 1.5

# A throttle is temporary and worth waiting out. The monthly quota is not --
# retrying that spends what little is left to no purpose, so it is raised.
_THROTTLE_ATTEMPTS = 4
_THROTTLE_BACKOFF = 5.0


def _is_throttle(response: httpx.Response) -> bool:
    """Whether a 429 is the per-second limit rather than the monthly quota.

    They arrive as the same status code and mean opposite things. The body is
    the only thing that distinguishes them:

        "You have exceeded the rate limit per second for your plan, PRO"

    When the wording changes the fallback is to treat it as the quota, which
    fails loudly instead of retrying into a wall.
    """
    return "per second" in response.text.lower()


async def _fetch(
    client: httpx.AsyncClient, key: str, url: str
) -> httpx.Response:
    """One request, waiting out the per-second throttle."""
    for attempt in range(1, _THROTTLE_ATTEMPTS + 1):
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
        if response.status_code != 429 or not _is_throttle(response):
            return response
        if attempt < _THROTTLE_ATTEMPTS:
            wait = _THROTTLE_BACKOFF * attempt
            logger.info("throttled; waiting %.0fs before retrying", wait)
            await asyncio.sleep(wait)
    return response


async def one_day(client: httpx.AsyncClient, key: str, day: date) -> list[RawFlight]:
    """Every movement through Ben Gurion on one date, both ends described.

    A 204 is an ANSWER, not a failure: the feed holds that date and has
    nothing for that window. 21 September 2026 returns one, correctly -- it
    was Yom Kippur and Ben Gurion was shut. An empty day is not always a gap,
    and treating it as one sends somebody hunting for data that never existed.
    """
    found: list[RawFlight] = []
    for start, end in _WINDOWS:
        url = (
            f"{DEFAULT_BASE_URL}/flights/airports/iata/{AIRPORT}"
            f"/{day.isoformat()}T{start}/{day.isoformat()}T{end}"
        )
        response = await _fetch(client, key, url)
        await asyncio.sleep(_PAUSE_SECONDS)

        if response.status_code in (204, 404):
            logger.info("%s %s-%s: the feed has nothing", day, start, end)
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
