"""The public board of recently disrupted flights.

    GET /api/v1/disruptions?days=2

WHAT THIS IS FOR
----------------
The landing page shows what has actually gone wrong at Ben Gurion in the last
day or two. It is the one part of the site that is evidence rather than
argument: a visitor who sees their own cancelled flight listed, priced, before
typing anything, does not need to be persuaded the service works.

WHY IT CAN BE REAL
------------------
Because the archive exists. Every fifteen minutes a cron writes the whole Ben
Gurion board into `flight_lookups`, so this endpoint is a QUERY over data we
already hold -- no API call, no quota, no vendor, and no hand-written table of
plausible-looking flights.

That is worth stating plainly because the obvious alternative is to fake it,
and a competitor's board carries "for illustration only" underneath. Ours does
not need to.

WHY IT IS CACHED FOR FIVE MINUTES
---------------------------------
The query walks a few thousand rows and runs the rules over each. That is fine
once a minute and wasteful once per visitor, and the answer only changes when
the archive runs -- every fifteen minutes. Five minutes is well inside that and
keeps a busy landing page from turning into a database load test.

WHAT IT DELIBERATELY DOES NOT DO
--------------------------------
Name a passenger, or promise anybody anything. A row here says what the board
recorded and what the bands would pay for a flight of that distance. Whether a
particular passenger is owed it depends on facts no board holds -- the notice
they were given, the reason the airline gives -- which is what the check is
for. The wording on the page says so.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Annotated, Final

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_session_factory
from app.tasks.disruptions import Disruption, find

logger = logging.getLogger("flight_system.api")

router = APIRouter(prefix="/api/v1/disruptions", tags=["disruptions"])

# The board is a shop window, not a report. Two days is what "recently" means
# to somebody whose flight was yesterday, and it keeps the table short enough
# to read without scrolling.
DEFAULT_DAYS: Final = 2
MAX_DAYS: Final = 14

# Every cancellation, and delays long enough to be worth somebody's attention.
# Below three hours nothing is payable under any of the three regimes, so a
# shorter delay on this board would be a row that can only disappoint.
MIN_DELAY_HOURS: Final = 3.0

# Long enough to stop a busy page hammering the database, short enough that the
# board never lags the archive by more than one of its own cycles.
CACHE_SECONDS: Final = 300

# The board scrolls, so it is a window onto a list rather than the whole
# list at once. Enough rows that the auto-scroll has somewhere to go and a
# visitor searching for their own flight has a fair chance of finding it.
MAX_ROWS: Final = 60


class DisruptionOut(BaseModel):
    """One row of the board."""

    flight_number: str
    flight_date: str
    origin: str
    destination: str
    airline: str
    status: str = Field(description="CANCELLED or DELAYED")
    delay_hours: float | None
    verdict: str
    amount: str | None = Field(
        description="Formatted band amount, e.g. ₪1,530. Null when the data "
        "cannot support a figure -- which is most inbound flights, because "
        "the board knows only the Ben Gurion end."
    )


class BoardOut(BaseModel):
    updated_at: str
    days: int
    rows: list[DisruptionOut]


@router.get("", response_model=BoardOut, summary="Recently disrupted flights")
def board(
    request: Request,
    factory: Annotated[sessionmaker[Session], Depends(get_session_factory)],
    days: Annotated[int, Query(ge=1, le=MAX_DAYS)] = DEFAULT_DAYS,
) -> BoardOut:
    """Cancellations and long delays from the archive, worst first.

    THE CACHE LIVES ON THE APP, NOT IN THIS MODULE.

    A module-level global would be the shorter spelling and is wrong in a way
    that is invisible until it is not: it outlives the application object, so
    a second app in the same process -- a test, a worker reusing an
    interpreter, a script importing the routes -- inherits the first one's
    answers about a database it has never seen. It was written that way first,
    and the tests below caught it immediately by getting an empty board back
    from a database that had rows in it.

    Hung off `app.state`, it is created with the app and dies with it.
    """
    cache: dict[int, tuple[datetime, BoardOut]] = getattr(
        request.app.state, "disruption_board_cache", None
    ) or {}
    request.app.state.disruption_board_cache = cache

    now = datetime.now(UTC)
    cached = cache.get(days)
    if cached is not None and (now - cached[0]).total_seconds() < CACHE_SECONDS:
        return cached[1]

    found = find(factory, min_delay_hours=MIN_DELAY_HOURS, days=days)

    # MOST RECENT FIRST, not worst first.
    #
    # `find` sorts by severity, which is right for a report somebody reads
    # top-down deciding what to chase. It is wrong for a board: with forty
    # cancellations in the window, every delay falls off the end and the
    # board reads as though nothing is ever merely late. Chronological mixes
    # them the way a real departures board does, and answers the question a
    # visitor actually has -- "did this happen to my flight, recently?"
    #
    # Within a day the worse event still leads.
    found.sort(key=lambda d: (d.flight_date, d.status == "CANCELLED"), reverse=True)

    payload = BoardOut(
        updated_at=now.isoformat(),
        days=days,
        rows=[_row(d) for d in found[:MAX_ROWS]],
    )
    cache[days] = (now, payload)
    logger.info("board: %d disruptions over %d day(s)", len(payload.rows), days)
    return payload


def _row(d: Disruption) -> DisruptionOut:
    origin, _, destination = d.route.partition(" → ")
    return DisruptionOut(
        flight_number=d.flight_number,
        flight_date=d.flight_date.isoformat(),
        origin=origin.strip(),
        destination=destination.strip(),
        # The carrier code is the front of the flight number: LY315 -> LY.
        # Taken from the number rather than the record because a row the
        # mapper rejected has no airline on it, and those rows still belong
        # on the board.
        airline=_carrier(d.flight_number),
        status="CANCELLED" if d.status == "CANCELLED" else "DELAYED",
        delay_hours=round(d.delay_hours, 1) if d.delay_hours is not None else None,
        verdict=d.verdict,
        amount=d.amount or None,
    )


def _carrier(flight_number: str) -> str:
    """The letters at the front of a flight number."""
    letters = ""
    for character in flight_number:
        if character.isdigit():
            break
        letters += character
    return letters or flight_number[:2]
