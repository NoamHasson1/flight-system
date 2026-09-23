"""Request and response shapes for the eligibility endpoint.

These are the public contract. Everything here is a Pydantic model, so the
OpenAPI document the frontend is written against is generated from the same
definitions the server validates with -- there is no second description of the
API to drift out of date.

Domain objects are deliberately not reused as response models. `FlightFacts`
and `EligibilityResult` are shaped for the rules; a response is shaped for
someone reading it. Coupling them would mean an internal rename becoming a
breaking API change.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.domain.models import Money

# Two letters or digits (IATA, "BA", "LY", "6H") or three letters (ICAO, "BAW"),
# then one to four digits, optionally an operational suffix letter.
_FLIGHT_NUMBER = re.compile(r"^[A-Z0-9]{2}[A-Z]?\d{1,4}[A-Z]?$")

# The longest limitation period in any jurisdiction we cover is six years
# (England and Wales). Beyond that there is nothing to claim, and asking the
# provider would spend money to say so.
MAX_AGE = timedelta(days=366 * 6)


class EligibilityRequest(BaseModel):
    """What the customer submits."""

    flight_number: str = Field(
        ..., min_length=3, max_length=10, examples=["BA165", "LY324"]
    )
    flight_date: date = Field(
        ...,
        description="The day the flight DEPARTED, in the departure airport's local date.",
        examples=["2026-08-14"],
    )

    # Optional, because the first thing a visitor does is check a flight and
    # demanding contact details before answering would lose most of them. They
    # are collected properly on the claim form, once there is something worth
    # claiming.
    contact_name: str | None = Field(default=None, max_length=200)
    contact_email: EmailStr | None = None

    # Set when re-asking after an AMBIGUOUS answer: the customer has picked
    # which of the matching flights was theirs.
    option_key: str | None = Field(default=None, max_length=64)

    @field_validator("flight_number")
    @classmethod
    def _valid_flight_number(cls, value: str) -> str:
        """Normalise and check the shape before spending an API call.

        Customers type "ba 165", "BA-165" and "ba165". All three are the same
        flight, and none of them should cost a lookup to find out.
        """
        cleaned = re.sub(r"[\s\-_.]", "", value).upper()
        if not _FLIGHT_NUMBER.match(cleaned):
            # HEBREW, because this reaches a customer verbatim.
            #
            # The frontend shows the server's own words for a 422 rather than
            # replacing them -- these messages say WHICH field is wrong and
            # why, which a generic client-side sentence cannot. That only
            # works while the server and the site speak the same language,
            # and the site is Hebrew.
            raise ValueError(
                f"‏{value!r} לא נראה כמו מספר טיסה. צריך קוד חברה ואחריו "
                f"ספרות, למשל LY315 או BZ 734."
            )
        return cleaned

    @field_validator("flight_date")
    @classmethod
    def _plausible_date(cls, value: date) -> date:
        """A flight that has not happened cannot have been delayed.

        This is the single most common user error -- entering the return date,
        or next year -- and catching it here gives a message that says so
        instead of "flight not found".
        """
        today = datetime.now().date()
        if value > today:
            raise ValueError(
                "התאריך הזה בעתיד. הזינו את היום שבו הטיסה המריאה — אפשר "
                "לבדוק רק טיסות שכבר יצאו."
            )
        if today - value > MAX_AGE:
            raise ValueError(
                "הטיסה הזו מלפני יותר משש שנים, מעבר לתקופת ההתיישנות בכל "
                "אחת מהמדינות שאנחנו מכסים."
            )
        return value


# --- Response pieces ---------------------------------------------------------


class MoneyOut(BaseModel):
    """An amount, three ways.

    `amount` is an exact decimal string, never a JSON number: JSON numbers are
    IEEE doubles in most parsers, and a payout that arrives in the browser as
    519.99999999 is the same bug Money exists to prevent, one layer further out.
    """

    amount: str = Field(examples=["520.00"])
    currency: str = Field(examples=["GBP"])
    formatted: str = Field(examples=["£520.00"])

    @classmethod
    def of(cls, money: Money | None) -> MoneyOut | None:
        if money is None:
            return None
        return cls(
            amount=str(money.amount), currency=money.currency.value, formatted=str(money)
        )


class OutcomeOut(BaseModel):
    """One regulation's answer.

    All three are always returned. An unexplained "no" destroys trust, and a
    customer who can see that two laws did not cover them and the third had a
    higher threshold understands the answer instead of doubting it.
    """

    regulation: str = Field(examples=["UK261"])
    verdict: str = Field(examples=["ELIGIBLE"])
    applies: bool = Field(
        description="Whether this law covered the flight at all, whatever it concluded."
    )
    reason: str
    award: MoneyOut | None = None
    open_question: str | None = Field(
        default=None,
        description=(
            "Set on LIKELY_ELIGIBLE: the one fact the passenger has to supply "
            "before this becomes a definite answer."
        ),
        examples=["cancellation_notice"],
    )


class FlightOut(BaseModel):
    """The flight as we understood it. Shown back so the customer can confirm
    we looked up the right one before building a claim on it."""

    flight_number: str
    flight_date: date
    airline: str
    route: str = Field(examples=["TLV → LHR"])
    origin: str
    origin_country: str
    destination: str
    destination_country: str
    distance_km: float
    status: str
    scheduled_departure: datetime | None
    scheduled_arrival: datetime | None
    actual_departure: datetime | None
    actual_arrival: datetime | None
    departure_delay_hours: float | None
    arrival_delay_hours: float | None


class FlightOptionOut(BaseModel):
    """One of several flights sharing a number on a date."""

    key: str
    route: str
    label: str = Field(examples=["DUB → STN, departing 16:00 UTC"])
    scheduled_departure: datetime | None


class EligibilityResponse(BaseModel):
    """The complete answer."""

    check_id: UUID = Field(description="Quote this when starting a claim.")
    status: str = Field(
        description="DECIDED | NOT_FOUND | AMBIGUOUS | UNRESOLVED",
        examples=["DECIDED"],
    )
    verdict: str | None = Field(
        default=None,
        description=(
            "ELIGIBLE | LIKELY_ELIGIBLE | NOT_ELIGIBLE | NEEDS_REVIEW. Null for "
            "NOT_FOUND and AMBIGUOUS, which are questions rather than answers. "
            "Neither NEEDS_REVIEW nor LIKELY_ELIGIBLE is a polite no: the first "
            "means we could not decide, the second means the law covers the "
            "flight and `best_award` is owed once the passenger answers "
            "`open_questions`."
        ),
    )
    message: str | None = None
    best_award: MoneyOut | None = None
    best_regulation: str | None = None
    flight: FlightOut | None = None
    outcomes: list[OutcomeOut] = []
    options: list[FlightOptionOut] = []
    open_questions: list[str] = Field(
        default=[],
        description=(
            "What to ask the passenger, each question once even when two laws "
            "wait on the same fact."
        ),
        examples=[["cancellation_notice"]],
    )
    caveat: str | None = None
    provider: str

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "check_id": "9e3eca9b-6f28-4370-a5a0-6fa224474f62",
                    "status": "DECIDED",
                    "verdict": "ELIGIBLE",
                    "best_award": {
                        "amount": "520.00", "currency": "GBP", "formatted": "£520.00"
                    },
                    "best_regulation": "UK261",
                    "provider": "fake",
                }
            ]
        }
    }


def flight_out(flight: Any) -> FlightOut:
    return FlightOut(
        flight_number=flight.flight_number,
        flight_date=flight.flight_date,
        airline=flight.airline_iata,
        route=flight.route,
        origin=flight.origin_iata,
        origin_country=flight.origin_country,
        destination=flight.destination_iata,
        destination_country=flight.destination_country,
        distance_km=round(flight.distance_km, 1),
        status=flight.status.value,
        scheduled_departure=flight.scheduled_departure,
        scheduled_arrival=flight.scheduled_arrival,
        actual_departure=flight.actual_departure,
        actual_arrival=flight.actual_arrival,
        departure_delay_hours=flight.departure_delay_hours,
        arrival_delay_hours=flight.arrival_delay_hours,
    )
