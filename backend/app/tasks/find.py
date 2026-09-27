"""Look inside the archive. Is this flight in there, and what does it say?

    python -m app.tasks.find HM9349
    python -m app.tasks.find HM9349 --date 2026-09-26
    python -m app.tasks.find --route TLV-SEZ --days 30
    python -m app.tasks.find --raw HM9349 --date 2026-09-26

WHY THIS EXISTS
---------------
Every question about whether the system is working turns out to be the same
question: IS THE FLIGHT IN THE ARCHIVE? Until now the only way to answer it
was to open a SQL client against production, which means the answer is
available to whoever writes SQL and to nobody else.

It is also the first thing to reach for when a customer says "your site
cannot find my flight". The three possible answers are completely different
problems and this tells them apart in one command:

    not in the archive          we never saw it -- a gap, or never published
    in the archive, unusable    we saw it but cannot read it -- a mapping bug
    in the archive and fine     the lookup path is broken, not the data

WHAT IT SHOWS
-------------
Every stored row, per source, with what each one says. Two sources
disagreeing is worth seeing directly rather than inferring from a verdict --
that is how the IZ164 contradiction was found.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta

from sqlalchemy import select

from app.api.deps import build_engine_and_factory
from app.config import get_settings
from app.db.models import FlightLookup
from app.providers.cache import _decode
from app.providers.mapper import MappingFailure, to_flight_facts


def _show(row: FlightLookup, *, raw: bool) -> None:
    flights = _decode(row.flights, row.provider)
    settled = "settled" if row.is_final else "not settled"
    print(
        f"\n  {row.flight_number}  {row.flight_date}  [{row.provider}]  "
        f"{settled}, seen {row.observed_at:%Y-%m-%d %H:%M} UTC"
    )
    if not flights:
        print("      (an empty answer: the source held that day and had nothing)")
        return

    for flight in flights:
        print(
            f"      {flight.origin_iata or '???'} → {flight.destination_iata or '???'}"
            f"   {flight.status}"
        )
        for label, value in (
            ("scheduled departure", flight.scheduled_departure),
            ("actual departure", flight.actual_departure),
            ("scheduled arrival", flight.scheduled_arrival),
            ("actual arrival", flight.actual_arrival),
        ):
            if value is not None:
                print(f"        {label:20} {value}")

        # Whether the rules could actually USE this row. A record that looks
        # complete here and still fails is the interesting case, and the
        # reason is printed rather than left to be guessed at.
        facts = to_flight_facts(flight)
        if isinstance(facts, MappingFailure):
            print("        usable by the rules?  NO")
            for problem in facts.problems:
                print(f"          - {problem}")
        else:
            print(f"        usable by the rules?  yes, {facts.distance_km:,.0f} km")

        if raw:
            print("        raw:")
            for line in json.dumps(flight.raw, indent=2, ensure_ascii=False).splitlines():
                print(f"          {line}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("flight_number", nargs="?", help="e.g. HM9349")
    parser.add_argument("--date", type=date.fromisoformat, metavar="YYYY-MM-DD")
    parser.add_argument("--route", help="e.g. TLV-SEZ, either direction")
    parser.add_argument("--days", type=int, default=14, help="how far back to look")
    parser.add_argument("--raw", action="store_true", help="print the source payload")
    parser.add_argument(
        "--day", type=date.fromisoformat, metavar="YYYY-MM-DD",
        help="list EVERY flight held for one day, the way the board published it",
    )
    args = parser.parse_args(argv)

    if not (args.flight_number or args.route or args.day):
        parser.error("give a flight number, --route, or --day")

    if args.day:
        return _whole_day(args.day)

    _, session_factory = build_engine_and_factory(get_settings())
    earliest = date.today() - timedelta(days=args.days)

    with session_factory() as session:
        query = select(FlightLookup).order_by(
            FlightLookup.flight_date, FlightLookup.provider
        )
        if args.flight_number:
            query = query.where(
                FlightLookup.flight_number == args.flight_number.strip().upper()
            )
        if args.date:
            query = query.where(FlightLookup.flight_date == args.date)
        elif not args.flight_number:
            query = query.where(FlightLookup.flight_date >= earliest)

        rows = list(session.scalars(query))

    if args.route:
        a, _, b = args.route.upper().partition("-")
        rows = [
            r
            for r in rows
            if any(
                {f.origin_iata, f.destination_iata} >= {a, b}
                for f in _decode(r.flights, r.provider)
            )
        ]

    if not rows:
        print("\n  Nothing in the archive matches.")
        print("  That means one of: we never captured it, the number is wrong,")
        print("  or the day is outside what we hold.\n")
        return 1

    print(f"\n  {len(rows)} row(s) in the archive:")
    for row in rows:
        _show(row, raw=args.raw)
    print()
    return 0


def _whole_day(day: date) -> int:
    """Everything the archive holds for one date, as a list a person can read.

    This is the answer to "how do I know I am seeing everything?". Counts
    prove a day is the right SIZE; only the list proves a particular flight
    is in it. Somebody who suspects a flight is missing can look, rather
    than being told a percentage.

    Sorted by scheduled time, like a departures board, because that is the
    order somebody scanning for their own flight expects.
    """
    _, session_factory = build_engine_and_factory(get_settings())
    with session_factory() as session:
        rows = list(
            session.scalars(
                select(FlightLookup)
                .where(FlightLookup.flight_date == day)
                .order_by(FlightLookup.flight_number)
            )
        )

    seen: dict[str, tuple[str, str, str]] = {}
    empty: list[str] = []
    for row in rows:
        flights = _decode(row.flights, row.provider)
        if not flights:
            empty.append(f"{row.flight_number} [{row.provider}]")
            continue
        for flight in flights:
            when = (
                flight.scheduled_departure or flight.scheduled_arrival
            )
            seen[row.flight_number] = (
                f"{when:%H:%M}" if when else "  --  ",
                f"{flight.origin_iata or '???'} → {flight.destination_iata or '???'}",
                str(flight.status),
            )

    print(f"\n  {day}: {len(seen)} flights held in the archive\n")
    for number, (when, route, status) in sorted(seen.items(), key=lambda kv: kv[1][0]):
        mark = "  *" if status in {"CANCELLED", "DIVERTED"} else "   "
        print(f"  {when}  {number:9} {route:14} {status}{mark}")

    if empty:
        # A row that exists and holds nothing. Either the source genuinely
        # had nothing, or an empty answer overwrote a real one -- which is a
        # bug that existed until 27 September and is worth seeing.
        print(f"\n  {len(empty)} row(s) present but EMPTY:")
        for name in empty:
            print(f"    {name}")

    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
