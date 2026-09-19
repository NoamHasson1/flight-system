"""Airport and airline reference data.

Two questions are answered here, and both decide real money:

* Where is this airport, and which country is it in?  -- the coordinates size
  the compensation band, and the country decides which law applies at all.
* Which state licensed this airline?  -- EC261 and UK261 only cover flights
  *arriving* into their territory when the operating carrier is one of theirs.

The data is committed into the repository rather than fetched at runtime. A
compensation decision must not depend on somebody else's web server being up.

Unknown codes return None. They do not raise. That is deliberate: an
unrecognised airport must become NEEDS_REVIEW, never a confident NOT_ELIGIBLE.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from app.domain.distance import haversine_km

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@dataclass(frozen=True, slots=True)
class Airport:
    """One airport. Coordinates and country come from the same row, so they
    cannot drift apart."""

    iata: str
    name: str
    country: str  # ISO 3166-1 alpha-2
    latitude: float
    longitude: float


@dataclass(frozen=True, slots=True)
class Airline:
    """One airline, and the state that issued its operating licence."""

    iata: str
    name: str
    country: str  # ISO 3166-1 alpha-2


def find_airport(iata: str) -> Airport | None:
    """Look up an airport by IATA code, or None if we do not know it."""
    return _airports().get(iata.strip().upper())


# The shortest name worth trying. Two or three letters are as likely to be a
# code, an abbreviation or noise as a place.
_MIN_NAME_LENGTH = 4


def find_airport_by_name(name: str) -> Airport | None:
    """Resolve an airport from a plain name -- ONLY when it cannot be anything
    else.

    A last resort, for records that carry a name and no code. Codeshare flight
    numbers do this routinely: AC5520 comes back with a full departure airport
    and an arrival of `{"name": "Newark"}`, nothing more. Refusing those means
    refusing every codeshare, and passengers book codeshares.

    Getting it wrong is expensive in a way that refusing is not. The
    destination decides which country is involved, therefore which law applies,
    and the distance, therefore how much is owed. So this matches only when
    exactly ONE airport can be meant:

        "Newark"    -> EWR, the only airport whose name starts that way
        "London"    -> None. Seven of them.
        "New York"  -> None. Two, and neither is the one a traveller means.

    That last case is the argument for the whole design. A match that merely
    looks confident would have sent a Newark passenger to a seaplane base.
    """
    words = tuple(name.strip().lower().split())
    if not words or len("".join(words)) < _MIN_NAME_LENGTH:
        return None

    matches = [
        airport
        for airport in _airports().values()
        if tuple(airport.name.strip().lower().split())[: len(words)] == words
    ]
    return matches[0] if len(matches) == 1 else None


def find_airline(iata: str) -> Airline | None:
    """Look up an airline by IATA code, or None if we do not know it."""
    return _airlines().get(iata.strip().upper())


def distance_between(origin: Airport, destination: Airport) -> float:
    """Great-circle distance in kilometres between two airports."""
    return haversine_km(
        origin.latitude, origin.longitude, destination.latitude, destination.longitude
    )


# --- loading -----------------------------------------------------------------
#
# Both files are read once, on first use, and cached for the life of the
# process. They are a few hundred kilobytes and never change while running.


@cache
def _airports() -> dict[str, Airport]:
    airports: dict[str, Airport] = {}
    for line_no, row in _rows("airports.csv"):
        iata = row["iata"].strip().upper()
        _reject_duplicate(airports, iata, "airports.csv", line_no)
        latitude, longitude = _coordinates(row, "airports.csv", line_no)
        airports[iata] = Airport(
            iata=iata,
            name=row["name"].strip(),
            country=row["country"].strip().upper(),
            latitude=latitude,
            longitude=longitude,
        )
    return airports


@cache
def _airlines() -> dict[str, Airline]:
    airlines: dict[str, Airline] = {}
    for line_no, row in _rows("airlines.csv"):
        iata = row["iata"].strip().upper()
        _reject_duplicate(airlines, iata, "airlines.csv", line_no)
        airlines[iata] = Airline(
            iata=iata,
            name=row["name"].strip(),
            country=row["country"].strip().upper(),
        )
    return airlines


def _rows(filename: str):  # type: ignore[no-untyped-def]
    """Yield (line number, row) from a data file, skipping `#` comment lines.

    csv has no concept of comments, so they are stripped before parsing. The
    line number is carried through purely so that a bad row names itself.
    """
    path = _DATA_DIR / filename
    with path.open(newline="", encoding="utf-8") as handle:
        lines = [line for line in handle if not line.lstrip().startswith("#")]
    for line_no, row in enumerate(csv.DictReader(lines), start=2):
        yield line_no, row


def _coordinates(
    row: dict[str, str], filename: str, line_no: int
) -> tuple[float, float]:
    try:
        latitude = float(row["latitude"])
        longitude = float(row["longitude"])
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{filename} line {line_no} ({row.get('iata')}): "
            f"unparseable coordinates"
        ) from exc
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError(
            f"{filename} line {line_no} ({row.get('iata')}): "
            f"coordinates out of range ({latitude}, {longitude})"
        )
    return latitude, longitude


def _reject_duplicate(
    seen: dict[str, object], iata: str, filename: str, line_no: int
) -> None:
    """Shipped data is ours, so a duplicate is a packaging mistake, not a user
    error. Fail loudly at load time rather than silently resolving a code to
    whichever row happened to come last."""
    if iata in seen:
        raise ValueError(f"{filename} line {line_no}: duplicate IATA code {iata!r}")
