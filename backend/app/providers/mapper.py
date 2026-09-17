"""Turning a provider's record into the facts the rules need.

This is the join between the two halves of the system. Above it, everything
speaks `FlightFacts` and knows nothing about vendors. Below it, adapters speak
`RawFlight` and know nothing about compensation. Enrichment happens here, once,
for every provider: airport codes become countries and coordinates, the pair
becomes a distance, and the airline becomes a licensing state.

WHY IT RETURNS A RESULT RATHER THAN RAISING
-------------------------------------------
Mapping fails for ordinary reasons. A provider can name an airport we do not
carry, an airline we have never heard of, or hand back a record with no
scheduled times at all. None of those is exceptional and none of them is the
customer's fault -- but every one of them would be catastrophic if it quietly
became NOT_ELIGIBLE.

So the failure is a value, not an exception: `MappingFailure` carries a reason
written for a person to read, and the layer above turns it into NEEDS_REVIEW.
Making the failure a normal return type means a caller cannot forget to handle
it the way a bare `except` lets you forget.

Every problem with a record is collected before returning, rather than stopping
at the first. "We do not recognise ZZZ or QQQ" is one round trip to fix; three
successive single-problem reports is three.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.domain.models import FlightFacts
from app.domain.reference import Airport, distance_between, find_airline, find_airport
from app.providers.base import RawFlight


@dataclass(frozen=True, slots=True)
class MappingFailure:
    """A provider record that cannot become FlightFacts, and why.

    `reason` is shown to the customer, so it is a complete sentence. `problems`
    is the machine-readable list behind it, for logging and for working out
    which reference data to extend.
    """

    reason: str
    problems: tuple[str, ...]
    raw: RawFlight

    @property
    def route(self) -> str:
        return self.raw.route


MappedFlight = FlightFacts | MappingFailure


def to_flight_facts(raw: RawFlight) -> MappedFlight:
    """Enrich one provider record, or explain why it cannot be enriched."""
    problems: list[str] = []

    origin = _airport(raw.origin_iata, "departure", problems)
    destination = _airport(raw.destination_iata, "arrival", problems)
    airline_country = _airline_country(raw.airline_iata, problems)

    # Scheduled times are the baseline every delay is measured against. Without
    # them there is no question to answer, only a guess to make.
    _require_time(raw.scheduled_departure, "scheduled departure", problems)
    _require_time(raw.scheduled_arrival, "scheduled arrival", problems)

    if origin is not None and destination is not None and origin == destination:
        # Not impossible in the wild -- a flight that returned to stand and was
        # logged as having arrived -- but the compensation question then becomes
        # "where was the final destination", which needs a person.
        problems.append(
            f"departure and arrival are both {origin.iata}, so there is no "
            f"journey to measure"
        )

    _check_ordering(raw, problems)

    if problems:
        return MappingFailure(
            reason=_readable(problems, raw), problems=tuple(problems), raw=raw
        )

    # Everything above has been checked; these cannot be None here.
    assert origin is not None and destination is not None
    assert airline_country is not None
    assert raw.scheduled_departure is not None and raw.scheduled_arrival is not None

    return FlightFacts(
        flight_number=raw.flight_number,
        flight_date=raw.flight_date,
        airline_iata=raw.airline_iata or "",
        airline_country=airline_country,
        origin_iata=origin.iata,
        origin_country=origin.country,
        destination_iata=destination.iata,
        destination_country=destination.country,
        distance_km=distance_between(origin, destination),
        scheduled_departure=raw.scheduled_departure,
        scheduled_arrival=raw.scheduled_arrival,
        actual_departure=raw.actual_departure,
        actual_arrival=raw.actual_arrival,
        status=raw.status,
    )


# --- The individual checks ---------------------------------------------------


def _airport(code: str | None, role: str, problems: list[str]) -> Airport | None:
    """Resolve an airport code to a country and a pair of coordinates.

    An unknown code is a gap in OUR data, not a fact about the customer's
    flight, and it must never be presented as one. The code is named in the
    problem so that the fix -- adding it to airports.csv -- is obvious.
    """
    if not code:
        problems.append(f"the provider did not give us an {role} airport")
        return None
    airport = find_airport(code)
    if airport is None:
        problems.append(f"we do not recognise the {role} airport {code}")
        return None
    return airport


def _airline_country(code: str | None, problems: list[str]) -> str | None:
    """Resolve the airline to the state that licensed it.

    Required even though only EC261 and UK261 consult it, and only for arrivals.
    We could guess that an unknown carrier is not an EU one -- but that guess
    fails in exactly one direction, turning "we have not heard of this airline"
    into "this airline is not European", which silently denies every arrival
    claim it touches. Asking a person is the only safe answer.
    """
    if not code:
        problems.append("the provider did not tell us which airline operated it")
        return None
    airline = find_airline(code)
    if airline is None:
        problems.append(f"we do not recognise the airline {code}")
        return None
    return airline.country


def _require_time(value: datetime | None, label: str, problems: list[str]) -> None:
    if value is None:
        problems.append(f"the provider did not give us a {label} time")


def _check_ordering(raw: RawFlight, problems: list[str]) -> None:
    """Catch timestamps that cannot both be true.

    A record where the aircraft arrives before it departs is corrupt, usually
    from a date or timezone mistake upstream. Left alone it produces a negative
    delay, which reads as a spectacularly early flight and a confident "no".
    """
    pairs = (
        (raw.scheduled_departure, raw.scheduled_arrival, "scheduled"),
        (raw.actual_departure, raw.actual_arrival, "actual"),
    )
    for departure, arrival, label in pairs:
        if departure is not None and arrival is not None and arrival <= departure:
            problems.append(
                f"the {label} arrival time is not after the {label} departure time"
            )


def _readable(problems: list[str], raw: RawFlight) -> str:
    """One sentence a customer can act on, or at least understand."""
    if len(problems) == 1:
        detail = problems[0]
    else:
        detail = "; ".join(problems[:-1]) + f"; and {problems[-1]}"
    return (
        f"We could not fully identify flight {raw.flight_number} "
        f"({raw.route}): {detail}. Someone will check this by hand."
    )
