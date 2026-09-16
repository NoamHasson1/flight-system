"""A readable way to construct FlightFacts in tests.

A rule test is about one sentence -- "a flight over 3,500 km that arrived four
hours late" -- and spelling that out as four timezone-aware datetimes buries the
point. This builder lets each test state only what it is actually testing and
inherit sane defaults for everything else.

Shared by the EC261, UK261, Israeli and engine test suites so that all four
describe flights the same way.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from app.domain.models import FlightFacts, FlightStatus

_FLIGHT_DATE = date(2026, 8, 14)
_SCHEDULED_DEPARTURE = datetime(2026, 8, 14, 10, 0, tzinfo=UTC)
_SCHEDULED_ARRIVAL = datetime(2026, 8, 14, 15, 0, tzinfo=UTC)


def a_flight(
    *,
    flight_number: str = "XX100",
    airline: str = "XX",
    airline_country: str = "IL",
    origin: str = "TLV",
    origin_country: str = "IL",
    destination: str = "LHR",
    destination_country: str = "GB",
    distance_km: float = 3588.6,
    arrival_delay_hours: float | None = 4.0,
    departure_delay_hours: float | None = None,
    status: FlightStatus = FlightStatus.LANDED,
) -> FlightFacts:
    """Build a flight described by its delays rather than its timestamps.

    `arrival_delay_hours=None` means the flight has no recorded arrival -- still
    in the air, or the provider simply did not tell us. `departure_delay_hours`
    defaults to the arrival delay, which is the ordinary case: a flight that
    leaves late and does not make up the time.
    """
    if departure_delay_hours is None:
        departure_delay_hours = arrival_delay_hours

    actual_departure = (
        None
        if departure_delay_hours is None
        else _SCHEDULED_DEPARTURE + timedelta(hours=departure_delay_hours)
    )
    actual_arrival = (
        None
        if arrival_delay_hours is None
        else _SCHEDULED_ARRIVAL + timedelta(hours=arrival_delay_hours)
    )

    return FlightFacts(
        flight_number=flight_number,
        flight_date=_FLIGHT_DATE,
        airline_iata=airline,
        airline_country=airline_country,
        origin_iata=origin,
        origin_country=origin_country,
        destination_iata=destination,
        destination_country=destination_country,
        distance_km=distance_km,
        scheduled_departure=_SCHEDULED_DEPARTURE,
        scheduled_arrival=_SCHEDULED_ARRIVAL,
        actual_departure=actual_departure,
        actual_arrival=actual_arrival,
        status=status,
    )
