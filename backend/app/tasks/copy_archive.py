"""Move the archive from one database to another, without losing any of it.

    python -m app.tasks.copy_archive --from sqlite:///./flight_system.db --dry-run
    python -m app.tasks.copy_archive --from sqlite:///./flight_system.db

The destination is DATABASE_URL, so this reads like "copy that archive into
where I am now".

WHY THIS EXISTS
---------------
The archive on a laptop is the only copy of what the Ben Gurion board published
on days that board has already forgotten. Moving to a server means either
carrying it across or starting from nothing, and starting from nothing throws
away the days nobody sells back.

An ordinary dump-and-restore does not work here: the source is SQLite and the
destination is PostgreSQL, with different types for uuid, timestamps and JSON.
This goes through the ORM so every value is converted by the same code that
wrote it.

WHAT IT WILL NOT DO
-------------------
Overwrite. A row already present in the destination is left exactly as it is --
the destination is the live archive, its copy of a flight is at least as recent
as this one, and a settled row there must not be replaced by an older view of
the same flight.

That makes it safe to run twice, and safe to run while the destination's own
archive job is working.

It copies ONLY `flight_lookups`. Checks and claims are customer records, and
moving those between databases is a migration to be done deliberately, not a
side effect of carrying flight data across.
"""

from __future__ import annotations

import argparse
import logging
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import build_engine_and_factory
from app.config import get_settings
from app.db.models import FlightLookup
from app.db.session import create_db_engine, create_session_factory

logger = logging.getLogger("flight_system.copy")


def copy(
    source_factory: sessionmaker[Session],
    destination_factory: sessionmaker[Session],
    *,
    dry_run: bool = False,
) -> tuple[int, int]:
    """Copy every flight-day the destination does not have. Returns
    (copied, already present)."""
    with source_factory() as source:
        rows = source.scalars(select(FlightLookup)).all()
        # Detached plain tuples rather than ORM objects: an instance still
        # attached to one session cannot be added to another, and expunging
        # them leaves lazy attributes that explode on first access.
        records = [
            (
                row.provider,
                row.flight_number,
                row.flight_date,
                row.observed_at,
                row.is_final,
                row.flights,
            )
            for row in rows
        ]

    logger.info("source holds %d flight-days", len(records))

    copied = skipped = 0
    with destination_factory() as destination:
        # One query for what is already there, rather than one per row: a
        # thousand round trips to a database in another country is the
        # difference between a minute and an hour.
        existing = {
            (provider, number, day)
            for provider, number, day in destination.execute(
                select(
                    FlightLookup.provider,
                    FlightLookup.flight_number,
                    FlightLookup.flight_date,
                )
            )
        }

        for provider, number, day, observed_at, is_final, flights in records:
            if (provider, number, day) in existing:
                skipped += 1
                continue
            copied += 1
            if dry_run:
                continue
            destination.add(
                FlightLookup(
                    provider=provider,
                    flight_number=number,
                    flight_date=day,
                    observed_at=observed_at,
                    is_final=is_final,
                    flights=flights,
                )
            )

        if dry_run:
            destination.rollback()
        else:
            destination.commit()

    logger.info(
        "%s %d flight-days (%d already present)",
        "would copy" if dry_run else "copied",
        copied,
        skipped,
    )
    return copied, skipped


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--from", dest="source", required=True, metavar="URL",
        help="the database to read from, e.g. sqlite:///./flight_system.db",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="report what would be copied and write nothing",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    settings = get_settings()
    _, destination_factory = build_engine_and_factory(settings)
    source_engine = create_db_engine(args.source)

    if args.source == settings.database_url:
        logger.error("source and destination are the same database")
        return 1

    try:
        copy(
            create_session_factory(source_engine),
            destination_factory,
            dry_run=args.dry_run,
        )
    except Exception:
        logger.exception("the copy failed; nothing was committed")
        return 1
    finally:
        source_engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
