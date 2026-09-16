"""The vocabulary the whole system speaks.

Everything here is a plain, immutable value object with no knowledge of HTTP,
databases or the flight-data provider. `FlightFacts` in particular is the single
input to every compensation rule -- no rule ever sees a vendor API response.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import Self

# --- Money -------------------------------------------------------------------


class Currency(StrEnum):
    EUR = "EUR"
    GBP = "GBP"
    ILS = "ILS"


_SYMBOLS: dict[Currency, str] = {
    Currency.EUR: "€",
    Currency.GBP: "£",
    Currency.ILS: "₪",
}


@dataclass(frozen=True, slots=True, order=False)
class Money:
    """An exact monetary amount. Never a float.

    Binary floating point cannot represent 0.1, so `0.1 + 0.2` is
    0.30000000000000004. That is a rounding error in someone's payout, so this
    type refuses floats entirely -- see `of()`.
    """

    amount: Decimal
    currency: Currency

    @classmethod
    def of(cls, amount: Decimal | int | str, currency: Currency) -> Self:
        """Build a Money, rejecting floats loudly.

        A float that reaches us has *already* lost precision. Converting it
        would only launder the error, so we refuse it and make the caller pass
        a string or a Decimal.
        """
        if isinstance(amount, float):
            raise TypeError(
                "Money rejects float to avoid rounding errors in payouts; "
                f"pass a str or Decimal instead of {amount!r}"
            )
        return cls(_to_2dp(Decimal(amount)), currency)

    def halved(self) -> Money:
        """Half the amount, rounded to the cent.

        Used by the Israeli Aviation Services Law, which halves compensation
        when the airline still lands the passenger reasonably close to on time.
        """
        return Money(_to_2dp(self.amount / 2), self.currency)

    def __str__(self) -> str:
        return f"{_SYMBOLS[self.currency]}{self.amount:,.2f}"


def _to_2dp(value: Decimal) -> Decimal:
    """Round to two decimal places, half-up.

    Half-up is what people expect and what invoices use. Python's default is
    banker's rounding (half-to-even), which would turn 2.5 into 2.
    """
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# --- Flights -----------------------------------------------------------------


class FlightStatus(StrEnum):
    """What actually happened to the flight."""

    SCHEDULED = "SCHEDULED"  # in the future, or not yet departed
    EN_ROUTE = "EN_ROUTE"  # airborne
    LANDED = "LANDED"  # arrived; the only status that can produce a payout
    CANCELLED = "CANCELLED"
    DIVERTED = "DIVERTED"  # landed somewhere else -- needs a human
    UNKNOWN = "UNKNOWN"  # the provider told us something we do not recognise


class Verdict(StrEnum):
    """The three possible answers. Three, not two -- deliberately.

    NEEDS_REVIEW exists because the dangerous failure in this system is a wrong
    NOT_ELIGIBLE: it costs the passenger real money and nobody ever finds out,
    because they simply close the tab. A wrong ELIGIBLE gets caught downstream
    by a human. So NOT_ELIGIBLE is only ever returned when the data is complete
    and a rule genuinely failed; anything missing or unrecognised goes to
    NEEDS_REVIEW instead.
    """

    ELIGIBLE = "ELIGIBLE"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    NEEDS_REVIEW = "NEEDS_REVIEW"


@dataclass(frozen=True, slots=True)
class FlightFacts:
    """Everything the rules need about one flight, and nothing else.

    Built by the provider layer from a vendor API response, then handed to the
    rules. All timestamps are timezone-aware; the constructor refuses naive ones
    because a naive/aware mix silently produces a wrong delay, which is exactly
    the bug that would pay someone nothing when they were owed 600 euro.
    """

    flight_number: str
    flight_date: date

    airline_iata: str
    airline_country: str  # ISO 3166-1 alpha-2 of the licensing state

    origin_iata: str
    origin_country: str
    destination_iata: str
    destination_country: str
    distance_km: float

    scheduled_departure: datetime
    scheduled_arrival: datetime
    status: FlightStatus
    actual_departure: datetime | None = None
    actual_arrival: datetime | None = None

    def __post_init__(self) -> None:
        for name in ("scheduled_departure", "scheduled_arrival"):
            _require_aware(name, getattr(self, name))
        for name in ("actual_departure", "actual_arrival"):
            value = getattr(self, name)
            if value is not None:
                _require_aware(name, value)

        if self.distance_km < 0:
            raise ValueError(f"distance_km cannot be negative, got {self.distance_km}")

        # Normalise codes here, at the boundary, so no rule has to wonder
        # whether it is comparing "TLV" with "tlv". frozen=True means we have to
        # go around the usual assignment machinery.
        for name in (
            "flight_number",
            "airline_iata",
            "airline_country",
            "origin_iata",
            "origin_country",
            "destination_iata",
            "destination_country",
        ):
            object.__setattr__(self, name, getattr(self, name).strip().upper())

    # --- delays ---
    #
    # Both are signed: a flight that arrives early gives a negative delay. The
    # rules only ever ask ">= 3 hours", so negatives are harmless, and keeping
    # the sign means the stored data tells the truth about what happened.

    @property
    def arrival_delay(self) -> timedelta | None:
        """How late the passenger actually got there. None if it has not landed.

        This is what EC261 and UK261 measure.
        """
        if self.actual_arrival is None:
            return None
        return self.actual_arrival - self.scheduled_arrival

    @property
    def departure_delay(self) -> timedelta | None:
        """How late the aircraft left. None if it has not departed.

        This is what the Israeli Aviation Services Law measures -- a different
        number from arrival delay, and not interchangeable with it.
        """
        if self.actual_departure is None:
            return None
        return self.actual_departure - self.scheduled_departure

    @property
    def arrival_delay_hours(self) -> float | None:
        return _to_hours(self.arrival_delay)

    @property
    def departure_delay_hours(self) -> float | None:
        return _to_hours(self.departure_delay)

    # --- shape of the data ---

    @property
    def is_cancelled(self) -> bool:
        return self.status is FlightStatus.CANCELLED

    @property
    def route(self) -> str:
        return f"{self.origin_iata} → {self.destination_iata}"

    @property
    def has_complete_timing(self) -> bool:
        """True when we know enough to decide, rather than to guess.

        A cancelled flight needs no actual times -- there are none. Anything
        else needs a real arrival time, otherwise the honest answer is
        NEEDS_REVIEW rather than NOT_ELIGIBLE.
        """
        if self.is_cancelled:
            return True
        return self.actual_arrival is not None


def _require_aware(field: str, value: datetime) -> None:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError(
            f"{field} must be timezone-aware; got the naive datetime {value!r}. "
            "Naive timestamps silently produce wrong delays."
        )


def _to_hours(delta: timedelta | None) -> float | None:
    return None if delta is None else delta.total_seconds() / 3600
