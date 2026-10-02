"""Reading the archive back, flight by flight.

WHAT THIS IS FOR

`app.tasks.find` already answers "what do we actually hold about this
flight?" from a terminal, and it has been the single most useful thing
during every debugging session: BZ887, HM9349, A45024, 6H502 were all
diagnosed by looking at the stored row rather than at the code.

This is the same question, reachable from a browser. The point is to
settle one argument quickly -- is a wrong answer our RULES being wrong,
or the DATA being thin? -- by showing exactly what the rules were given,
including whether they could use it at all.

WHY IT READS flight_lookups AND NOT eligibility_checks

A check only exists if somebody asked. The archive holds every flight the
board has published since we started recording, asked about or not, so a
flight can be examined before any customer ever types its number -- which
is the whole point of a troubleshooting tool.

THE DATE RANGE IS NOT OPTIONAL WHEN BROWSING

There are fifteen thousand rows and each one holds a JSON list that has
to be decoded to know whether the flight was disrupted. Decoding all of
them on every page view would make the page slow in a way that gets worse
every single day the archive grows. A flight number is indexed and cheap;
browsing is bounded by dates.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import FlightLookup
from app.providers.base import RawFlight
from app.providers.cache import _decode
from app.providers.mapper import MappingFailure, to_flight_facts

# What counts as worth showing when browsing rather than searching. Not a
# legal threshold -- the laws start at three hours -- but the point of the
# browse list is "what happened today", and a flight fifteen minutes late
# is part of what happened.
DISRUPTED_MINUTES = 15.0

# How many days a browse covers when nothing is specified.
#
# Measured before changing it, which is the only reason it is still seven.
# A week is 7,200 archived rows, and the obvious suspicion -- that
# decoding all of them is what makes the page slow -- is wrong:
#
#     7 days: 7,212 rows   fetch 0.70s   decode and map 0.04s
#
# The decode is free. The cost is fetching the rows, and from a laptop
# that is a link to Frankfurt; on Render the database is next door.
DEFAULT_DAYS = 7

# A backstop, not the real bound. The DATE RANGE is what keeps this cheap,
# exactly as it does for `app.tasks.disruptions.find`, which scans the same
# table the same way in production.
#
# The first version capped the scan at 400 ROWS instead, before the
# disruption filter ran -- so browsing sorted newest-first, took 400 rows of
# FUTURE scheduled flights, found that none of them had been disrupted yet,
# and reported an empty week. A limit applied before a filter is a limit on
# the wrong thing.
MAX_SCAN = 20_000

# Sorts before any real flight, and is timezone-aware so it can be compared
# with one.
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class ArchivedFlight:
    """One source's record of one flight, flattened for display.

    Flat rather than nested because the screen is a table: the operator is
    comparing the same field down a column, and anything that has to be
    unwrapped first is a field they cannot compare.
    """

    provider: str
    observed_at: datetime
    is_final: bool

    flight_number: str
    flight_date: date
    airline_iata: str | None
    origin_iata: str | None
    destination_iata: str | None
    status: str

    scheduled_departure: datetime | None
    actual_departure: datetime | None
    scheduled_arrival: datetime | None
    actual_arrival: datetime | None

    departure_delay_minutes: float | None
    arrival_delay_minutes: float | None

    # THE MOST USEFUL FIELD ON THE SCREEN.
    #
    # A record can look complete and still be unusable -- no arrival
    # airport, an unknown IATA code, an arrival before its departure. When
    # a customer is told "we could not find your flight" and the row is
    # plainly sitting here, this is the line that explains it.
    usable: bool
    unusable_reason: str | None
    distance_km: float | None

    raw: dict[str, object]


def _delay_minutes(scheduled: datetime | None, actual: datetime | None) -> float | None:
    if scheduled is None or actual is None:
        return None
    return (actual - scheduled).total_seconds() / 60


def _flatten(row: FlightLookup, flight: RawFlight) -> ArchivedFlight:
    facts = to_flight_facts(flight)
    failed = isinstance(facts, MappingFailure)
    return ArchivedFlight(
        provider=row.provider,
        observed_at=row.observed_at,
        is_final=row.is_final,
        flight_number=flight.flight_number,
        flight_date=flight.flight_date,
        airline_iata=flight.airline_iata,
        origin_iata=flight.origin_iata,
        destination_iata=flight.destination_iata,
        status=flight.status.value,
        scheduled_departure=flight.scheduled_departure,
        actual_departure=flight.actual_departure,
        scheduled_arrival=flight.scheduled_arrival,
        actual_arrival=flight.actual_arrival,
        departure_delay_minutes=_delay_minutes(
            flight.scheduled_departure, flight.actual_departure
        ),
        arrival_delay_minutes=_delay_minutes(
            flight.scheduled_arrival, flight.actual_arrival
        ),
        usable=not failed,
        unusable_reason=facts.reason if failed else None,
        distance_km=None if failed else facts.distance_km,
        raw=dict(flight.raw),
    )


def _is_disrupted(flight: ArchivedFlight) -> bool:
    if flight.status in ("CANCELLED", "DIVERTED"):
        return True
    return any(
        delay is not None and delay >= DISRUPTED_MINUTES
        for delay in (flight.departure_delay_minutes, flight.arrival_delay_minutes)
    )


def search_flights(
    session: Session,
    *,
    number: str | None = None,
    on: date | None = None,
    since: date | None = None,
    until: date | None = None,
    disrupted_only: bool = False,
    limit: int = 100,
    offset: int = 0,
    max_scan: int = MAX_SCAN,
) -> tuple[list[ArchivedFlight], bool, int]:
    """What the archive holds, newest day first.

    Returns the page of rows, whether the SCAN was cut short, and how many
    matched in total.

    The total is the point. A day at Ben Gurion is around 870 flights, and
    a screen that shows 200 of them without saying so is the failure this
    whole module exists to avoid -- somebody browses, does not find a
    flight, and concludes we never recorded it. With the total they know
    to keep paging; with the scan flag they know when even the total is
    understated.

    A flight number alone searches the WHOLE archive -- that is the
    troubleshooting case and the column is indexed. Without one, the
    search is bounded by dates.

    `max_scan` is a backstop and exists as a parameter so a test can set
    it low. The bug it guards against -- a scan cap applied before the
    disruption filter -- cannot be reproduced at the real value without
    inserting twenty thousand rows.
    """
    stmt = select(FlightLookup)

    if number:
        stmt = stmt.where(FlightLookup.flight_number == number.strip().upper())
    if on:
        stmt = stmt.where(FlightLookup.flight_date == on)
    elif not number:
        # Only bound by dates when there is no flight number to make the
        # query cheap on its own.
        if since:
            stmt = stmt.where(FlightLookup.flight_date >= since)
        if until:
            stmt = stmt.where(FlightLookup.flight_date <= until)

    # One more than the cap, so hitting it is DETECTABLE.
    #
    # A scan cap sits before the disruption filter -- it has to, the filter
    # needs the decoded payload -- so a cap that bites silently drops
    # matching flights. On a screen whose whole job is answering "do we
    # have this flight?", an incomplete answer that looks complete is the
    # worst thing it can produce: somebody reads "no record" and tells a
    # customer we have nothing.
    #
    # So the cap is high enough that a date-bounded browse never reaches
    # it, and reaching it is reported rather than hidden.
    rows = session.scalars(
        stmt.order_by(
            FlightLookup.flight_date.desc(), FlightLookup.flight_number
        ).limit(max_scan + 1)
    ).all()
    scan_was_cut = len(rows) > max_scan
    rows = rows[:max_scan]

    found: list[ArchivedFlight] = []
    for row in rows:
        for flight in _decode(row.flights, row.provider):
            record = _flatten(row, flight)
            if disrupted_only and not _is_disrupted(record):
                continue
            found.append(record)

    # `EPOCH`, not `datetime.min`. Every stored time is timezone-aware, and
    # comparing an aware datetime to a naive one raises TypeError -- so a
    # single record with neither a scheduled departure nor a scheduled
    # arrival would crash the whole page. Those exist: a cancellation the
    # board publishes with no times at all.
    found.sort(
        key=lambda f: (
            f.flight_date,
            f.scheduled_departure or f.scheduled_arrival or EPOCH,
        ),
        reverse=True,
    )
    return found[offset : offset + limit], scan_was_cut, len(found)
