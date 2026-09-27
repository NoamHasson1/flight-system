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
    words = _significant(name)
    if not words or len("".join(words)) < _MIN_NAME_LENGTH:
        return None

    # FIRST: the name is the start of an airport's name. "Newark" ->
    # "Newark Liberty International Airport". This is the common shape and
    # the strictest reading, so it is tried before anything looser.
    prefixed = [
        airport
        for airport in _airports().values()
        if tuple(airport.name.strip().lower().split())[: len(words)] == words
    ]
    if len(prefixed) == 1:
        return prefixed[0]
    if prefixed:
        # Several airports start this way. Ambiguous is ambiguous; looking
        # harder would only find a way to guess.
        return None

    # SECOND: the airport's name is CONTAINED in what we were given.
    #
    # Real example, and the reason this exists: AeroDataBox returns the
    # arrival of a codeshare as {"name": "Mahe Seychelles Via Mauritius"}.
    # The destination is Mahé -- SEZ, "Seychelles International Airport" --
    # but the string is a route description, so no airport name begins with
    # it and the prefix rule above finds nothing.
    #
    # The direction matters and only one of the two is safe.
    #
    #   airport name inside the given name   -> safe
    #   given name inside an airport name    -> NOT safe
    #
    # The second would resolve "New York" to the one airport whose name
    # happens to contain both words -- a seaplane base -- and send a
    # passenger's claim to the wrong country. So it is not attempted.
    #
    # Generic words are dropped from both sides first, because "airport" and
    # "international" appear in three thousand names and carry no
    # information; leaving them in makes a short real name look like a match
    # for everything.
    query = set(words)
    contained = [
        airport
        for airport in _airports().values()
        if (core := _significant(airport.name)) and set(core) <= query
    ]
    return contained[0] if len(contained) == 1 else None


# Words that appear in thousands of airport names and distinguish nothing.
# "Via" is different in kind -- it is not part of a name at all, it is the
# routing of a multi-leg flight, and everything after it is a place the
# passenger does not end up. Dropped for the same reason: it is noise that
# stops a real name being recognised.
_GENERIC = frozenset(
    {
        "airport",
        "international",
        "intl",
        "regional",
        "municipal",
        "national",
        "field",
        "the",
        "of",
        "and",
        "de",
        "del",
        "di",
        "da",
        "el",
        "la",
        "le",
        "via",
    }
)


def _significant(name: str) -> tuple[str, ...]:
    """The words in a name that actually identify a place.

    Everything from "via" onwards is dropped entirely, not just the word:
    "Mahe Seychelles Via Mauritius" is a journey through Mauritius ending at
    Mahé, and matching on Mauritius would name the wrong country, the wrong
    law and the wrong distance.
    """
    words = name.strip().lower().replace(",", " ").split()
    if "via" in words:
        words = words[: words.index("via")]
    return tuple(w for w in words if w not in _GENERIC and not w.isdigit())


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
