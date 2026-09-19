"""The port: what the rest of the system requires of a flight-data source.

WHY THIS LAYER EXISTS
---------------------
The system must not care where flight data comes from. Providers get discontinued,
repriced, rate-limited and occasionally just wrong, and a compensation engine
welded to one vendor's JSON is a liability.

So this module defines a *port* -- a narrow contract -- and each vendor gets an
*adapter* implementing it. Nothing above this layer ever imports a vendor module
or sees a vendor field name.

    app/providers/
        base.py           <- this file: the contract, shared by everyone
        fake.py           <- adapter: scripted scenarios, no network
        aerodatabox.py    <- adapter: the real thing (step 11)
        mapper.py         <- RawFlight + reference data -> FlightFacts (step 12)

TO ADD A NEW PROVIDER
---------------------
1. Write `app/providers/<vendor>.py` with a class satisfying `FlightDataProvider`.
2. Translate that vendor's payload into `RawFlight`. That is the only work.
3. Register it in the provider registry (step 11) so config can select it.

No rule, no endpoint and no test outside that file changes. Enrichment --
airports, countries, distance -- happens once, downstream, for every provider.

WHY `RawFlight` AND NOT `FlightFacts`
-------------------------------------
If a provider produced finished `FlightFacts`, every new provider would have to
re-implement airport lookup, country resolution and great-circle distance, and
they would drift. A provider does exactly one job: translate its own JSON into a
common shape. Everything else is shared.

`RawFlight` fields are therefore optional. Providers differ in completeness, and
it is not the adapter's place to decide what a missing arrival time means -- that
judgement belongs to the mapper, which turns absent data into NEEDS_REVIEW.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Protocol, runtime_checkable

from app.domain.models import FlightStatus


@dataclass(frozen=True, slots=True)
class RawFlight:
    """One flight as a provider described it: normalised in shape, not enriched.

    Everything optional except the identity of the flight itself, because
    providers vary in what they return and an adapter must never invent a value
    to fill a gap. A missing field travels as None and the mapper decides what
    it means.
    """

    flight_number: str
    flight_date: date
    status: FlightStatus
    provider: str

    airline_iata: str | None = None
    origin_iata: str | None = None
    destination_iata: str | None = None

    # All timezone-aware UTC. Converting local times is the adapter's job,
    # done once at the edge, because FlightFacts refuses naive datetimes and a
    # naive/aware mix silently produces a wrong delay.
    scheduled_departure: datetime | None = None
    actual_departure: datetime | None = None
    scheduled_arrival: datetime | None = None
    actual_arrival: datetime | None = None

    # The untouched vendor payload. Stored with every check so that a decision
    # can be re-explained, or re-run against corrected rules, without paying the
    # provider again. Never read by any rule.
    raw: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in (
            "scheduled_departure",
            "actual_departure",
            "scheduled_arrival",
            "actual_arrival",
        ):
            value = getattr(self, name)
            if value is not None and (
                value.tzinfo is None or value.tzinfo.utcoffset(value) is None
            ):
                raise ValueError(
                    f"{self.provider}: {name} must be timezone-aware, got {value!r}. "
                    "Adapters convert local times to UTC at the edge."
                )

    @property
    def route(self) -> str:
        return f"{self.origin_iata or '???'} → {self.destination_iata or '???'}"


@runtime_checkable
class FlightDataProvider(Protocol):
    """The contract every flight-data adapter satisfies."""

    name: str

    async def fetch(
        self, flight_number: str, flight_date: date
    ) -> Sequence[RawFlight]:
        """Return every flight matching this number on this date.

        A SEQUENCE, not a single flight, and that is deliberate. One flight
        number on one date can legitimately match more than one flight: a
        multi-leg service such as TLV-LHR-JFK, or a route flown twice in a day.
        Silently picking the first would produce a confidently wrong answer for
        anybody on the other one, so the caller is made to deal with it.

        An EMPTY sequence means "no such flight" -- an answer, not a failure.
        Failures raise. The distinction matters: "we looked and it is not there"
        is a 404 the customer can act on, while "we could not look" must never
        be presented as though we had.
        """
        ...


# --- Failures ----------------------------------------------------------------
#
# Every one of these means we could not get an answer, NOT that the answer was
# no. They exist as distinct types so the layer above can map all of them to
# NEEDS_REVIEW while still logging and reporting them differently.


class FlightDataError(Exception):
    """Base for every provider failure. Catch this to be safe by default."""


class ProviderUnavailable(FlightDataError):
    """The provider could not be reached, timed out, or returned a 5xx."""


class ProviderRateLimited(FlightDataError):
    """We are over quota. Distinct from unavailable: retrying will not help
    now, and it is an operational signal that the plan needs upgrading."""


class ProviderAuthError(FlightDataError):
    """The API key is missing, wrong, or not subscribed to this product.

    Its own type because it is the one failure a developer can fix in a minute,
    and it must never be buried in a generic "unavailable".
    """


class ProviderCoverageGap(FlightDataError):
    """The provider answered, and its data does not reach that far.

    Distinct from an empty result, and the distinction is the whole point. An
    empty result means "we looked at the days we hold and the flight is not
    among them" -- an answer. This means "those days are not ours to look at",
    which must never be dressed up as a no. A national airport board publishing
    a rolling five-day window is the ordinary case.
    """


class ProviderResponseInvalid(FlightDataError):
    """The provider answered, but not in a shape we recognise.

    A signal that the vendor changed their schema. Loud on purpose: silently
    coercing an unrecognised payload is how wrong verdicts get shipped.
    """
