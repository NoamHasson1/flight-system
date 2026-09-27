"""Did the archive actually record what the board published?

    python -m app.tasks.coverage
    python -m app.tasks.coverage --email

WHY THIS EXISTS
---------------
Everything else in this system assumes the archive is complete. Nothing
checked that it was.

The failure it catches is silent by construction. A cron that stops firing
produces no error; a day captured at half strength looks exactly like a quiet
Saturday; a dataset that moves produces zero rows and no exception. In every
case the system keeps answering questions, confidently, from a record with
holes in it -- and the only symptom is a customer being told "no flight
found" for a flight that certainly happened.

HOW IT CAN CHECK AT ALL
-----------------------
Because the board keeps about four days. While a day is still published, the
same question can be asked twice:

    how many flights does the board list for that day?
    how many does our archive hold for it?

Same source, same day, two numbers that should agree. That is the whole idea,
and it costs one HTTP request -- no key, no quota.

Once the board drops a day the comparison is impossible forever, which is why
this runs daily rather than when somebody wonders.

WHAT A DIFFERENCE MEANS
-----------------------
    archive < board    rows were missed. The cron was down, or is failing.
    archive > board    NORMAL, and not a fault: the board sheds the past
                       continuously, so a day we captured in full this
                       morning is already thinner on the board by tonight.
                       Holding MORE than the board is the archive doing its
                       job.

So only a shortfall is a problem, and it is reported as a percentage of what
the board currently shows.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from collections import Counter
from datetime import date

from sqlalchemy import func, select

from app.api.deps import build_engine_and_factory
from app.config import get_settings
from app.db.models import FlightLookup
from app.email.registry import build_email_sender
from app.email.base import EmailMessage
from app.providers.iaa import IsraelAirportsProvider

logger = logging.getLogger("flight_system.coverage")

# Below this share of what the board shows, a day is reported as short.
# Not 100%: the board is a live document and a flight can appear between our
# last run and this check, so a couple of rows' difference is normal weather
# rather than a fault.
HEALTHY = 0.97


async def compare() -> list[tuple[date, int, int]]:
    """(day, on the board, in the archive) for every day the board still holds."""
    board = await IsraelAirportsProvider().snapshot()
    published = Counter(f.flight_date for f in board)

    settings = get_settings()
    _, session_factory = build_engine_and_factory(settings)
    with session_factory() as session:
        held = dict(
            session.execute(
                select(FlightLookup.flight_date, func.count())
                .where(FlightLookup.flight_date.in_(published))
                .group_by(FlightLookup.flight_date)
            ).all()
        )

    return [(day, published[day], held.get(day, 0)) for day in sorted(published)]


def report(rows: list[tuple[date, int, int]]) -> tuple[str, bool]:
    """The lines a person reads, and whether anything is wrong."""
    lines: list[str] = []
    short = False
    for day, on_board, archived in rows:
        ratio = archived / on_board if on_board else 1.0
        ok = ratio >= HEALTHY
        short = short or not ok
        lines.append(
            f"  {day}  {archived:5} archived / {on_board:5} on the board   "
            f"{'OK' if ok else f'SHORT by {on_board - archived}'}"
        )
    return "\n".join(lines), short


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--email", action="store_true",
        help="send the report to OPS_EMAIL as well as printing it",
    )
    parser.add_argument(
        "--only-when-short", action="store_true",
        help="with --email, write only when something is wrong",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    try:
        rows = asyncio.run(compare())
    except Exception:
        # A check that cannot run is itself news: it usually means the board
        # moved or went away, which is the largest failure this system has.
        logger.exception("the coverage check could not run")
        return 1

    body, short = report(rows)
    print(body)
    logger.info("coverage: %s", "SHORT" if short else "complete")

    if args.email and (short or not args.only_when_short):
        settings = get_settings()
        if not settings.ops_email.strip():
            logger.warning("no OPS_EMAIL configured; not sending")
            return 0
        headline = "חסרות טיסות בארכיון" if short else "הארכיון שלם"
        sender = build_email_sender(settings.email_sender, settings)
        sender.send(
            EmailMessage(
                to=settings.ops_email.strip(),
                subject=f"[Skyclaim] כיסוי הארכיון · {headline}",
                text=(
                    f"{headline}\n\n{body}\n\n"
                    "מושווה מול לוח הטיסות הרשמי של נתב״ג, שמחזיק כארבעה ימים.\n"
                    "יותר בארכיון מאשר בלוח זה תקין — הלוח משיל את העבר.\n"
                ),
                html=(
                    f'<p style="font-weight:700">{headline}</p>'
                    f'<pre style="font-family:ui-monospace,monospace;font-size:13px">'
                    f"{body}</pre>"
                    '<p style="color:#5B6470;font-size:13px">מושווה מול לוח הטיסות '
                    "הרשמי של נתב״ג, שמחזיק כארבעה ימים. יותר בארכיון מאשר בלוח "
                    "זה תקין — הלוח משיל את העבר.</p>"
                ),
            )
        )

    return 2 if short else 0


if __name__ == "__main__":
    sys.exit(main())
