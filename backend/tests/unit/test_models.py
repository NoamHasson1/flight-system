"""Tests for the domain value objects.

Two themes run through these: money must never lose a cent, and a delay must
never be computed from timestamps we do not fully trust.
"""

from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.domain.models import Currency, FlightFacts, FlightStatus, Money, Verdict


def facts(**overrides: object) -> FlightFacts:
    """A landed TLV->LHR flight, 4 hours late. Overridable per test."""
    base: dict[str, object] = {
        "flight_number": "BA165",
        "flight_date": date(2026, 8, 14),
        "airline_iata": "BA",
        "airline_country": "GB",
        "origin_iata": "TLV",
        "origin_country": "IL",
        "destination_iata": "LHR",
        "destination_country": "GB",
        "distance_km": 3588.7,
        "scheduled_departure": datetime(2026, 8, 14, 10, 0, tzinfo=UTC),
        "scheduled_arrival": datetime(2026, 8, 14, 15, 0, tzinfo=UTC),
        "actual_departure": datetime(2026, 8, 14, 14, 0, tzinfo=UTC),
        "actual_arrival": datetime(2026, 8, 14, 19, 0, tzinfo=UTC),
        "status": FlightStatus.LANDED,
    }
    base.update(overrides)
    return FlightFacts(**base)  # type: ignore[arg-type]


# --- Money -------------------------------------------------------------------


def test_money_rejects_float() -> None:
    """The single most important test in this file.

    Binary floating point cannot represent 0.1 exactly. If a float ever reaches
    a payout amount, the error is already baked in and silently converting it
    would only hide that. Refusing it forces callers to use str or Decimal.
    """
    with pytest.raises(TypeError, match="rejects float"):
        Money.of(250.5, Currency.EUR)  # type: ignore[arg-type]


@pytest.mark.parametrize("value", ["250", 250, Decimal("250")])
def test_money_accepts_exact_types(value: Decimal | int | str) -> None:
    """str, int and Decimal all produce the identical exact amount."""
    assert Money.of(value, Currency.EUR).amount == Decimal("250.00")


def test_money_keeps_cents_exactly() -> None:
    """A value that a float would mangle survives intact."""
    assert Money.of("0.10", Currency.EUR).amount + Money.of(
        "0.20", Currency.EUR
    ).amount == Decimal("0.30")


@pytest.mark.parametrize(
    ("amount", "expected"),
    [("1530", "765.00"), ("2450", "1225.00"), ("3670", "1835.00"), ("0.05", "0.03")],
)
def test_money_halved(amount: str, expected: str) -> None:
    """The Israeli 50% reduction.

    The three real shekel amounts halve exactly. The 0.05 case pins the rounding
    policy: half-up gives 0.03, while Python's default banker's rounding would
    give 0.02. Consistently rounding a passenger down would be indefensible.
    """
    assert Money.of(amount, Currency.ILS).halved().amount == Decimal(expected)


def test_money_is_immutable() -> None:
    """Amounts must not be mutable in place; a payout is a fact, not a variable."""
    with pytest.raises(AttributeError):
        Money.of("250", Currency.EUR).amount = Decimal("999")  # type: ignore[misc]


def test_money_equality_is_currency_aware() -> None:
    """250 euro is not 250 pounds, however tempting the arithmetic."""
    assert Money.of("250", Currency.EUR) != Money.of("250", Currency.GBP)


@pytest.mark.parametrize(
    ("currency", "expected"),
    [(Currency.EUR, "€600.00"), (Currency.GBP, "£520.00"), (Currency.ILS, "₪2,450.00")],
)
def test_money_formatting(currency: Currency, expected: str) -> None:
    amount = {"EUR": "600", "GBP": "520", "ILS": "2450"}[currency.value]
    assert str(Money.of(amount, currency)) == expected


# --- Timezone safety ---------------------------------------------------------


@pytest.mark.parametrize(
    "field",
    ["scheduled_departure", "scheduled_arrival", "actual_departure", "actual_arrival"],
)
def test_naive_datetimes_are_rejected(field: str) -> None:
    """The bug this prevents is silent and expensive.

    Aviation feeds mix local and UTC times freely. Subtracting a naive datetime
    from an aware one raises TypeError; subtracting two naive ones from
    different zones quietly returns a wrong delay -- which could pay a passenger
    nothing when they were owed 600 euro. So the object refuses to exist.
    """
    with pytest.raises(ValueError, match="timezone-aware"):
        facts(**{field: datetime(2026, 8, 14, 12, 0)})


def test_delays_are_correct_across_timezones() -> None:
    """Scheduled in one offset, actual in another: the delay is still right.

    Scheduled arrival 15:00 UTC, actual arrival 18:00 in UTC+2 (= 16:00 UTC),
    so the true delay is 1 hour -- not the 3 hours a naive string comparison of
    "15:00" and "18:00" would suggest.
    """
    f = facts(
        scheduled_arrival=datetime(2026, 8, 14, 15, 0, tzinfo=UTC),
        actual_arrival=datetime(2026, 8, 14, 18, 0, tzinfo=timezone(timedelta(hours=2))),
    )
    assert f.arrival_delay_hours == 1.0


# --- Delays ------------------------------------------------------------------


def test_arrival_and_departure_delays_are_different_numbers() -> None:
    """The classic mistake in this domain, pinned in one test.

    This flight left 4 hours late and landed 4 hours late, but they are computed
    from different pairs of timestamps and must never be conflated: EC261/UK261
    read arrival, the Israeli law reads departure.
    """
    f = facts()
    assert f.arrival_delay_hours == 4.0
    assert f.departure_delay_hours == 4.0
    assert f.arrival_delay == timedelta(hours=4)


def test_pilot_makes_up_time() -> None:
    """Left 5 hours late, landed 2 hours late.

    Under EC261 this passenger gets nothing, because compensation is measured at
    arrival. An implementation reading departure delay would wrongly pay out.
    """
    f = facts(
        actual_departure=datetime(2026, 8, 14, 15, 0, tzinfo=UTC),
        actual_arrival=datetime(2026, 8, 14, 17, 0, tzinfo=UTC),
    )
    assert f.departure_delay_hours == 5.0
    assert f.arrival_delay_hours == 2.0


def test_early_arrival_gives_a_negative_delay() -> None:
    """Signed, not clamped -- the stored data should tell the truth."""
    f = facts(actual_arrival=datetime(2026, 8, 14, 14, 30, tzinfo=UTC))
    assert f.arrival_delay_hours == -0.5


def test_delay_is_none_when_the_flight_has_not_landed() -> None:
    """None, never zero.

    Zero would read as "on time" and produce a confident NOT_ELIGIBLE for a
    flight that is still in the air.
    """
    f = facts(status=FlightStatus.EN_ROUTE, actual_arrival=None)
    assert f.arrival_delay_hours is None


# --- Completeness, which drives NEEDS_REVIEW ---------------------------------


def test_missing_arrival_time_is_incomplete() -> None:
    """Drives the three-way verdict: incomplete data must not become a "no"."""
    assert facts(actual_arrival=None).has_complete_timing is False


def test_cancelled_flight_is_complete_without_actual_times() -> None:
    """A cancelled flight has no actual times and never will.

    Treating it as incomplete would send every cancellation to manual review.
    """
    f = facts(status=FlightStatus.CANCELLED, actual_departure=None, actual_arrival=None)
    assert f.is_cancelled is True
    assert f.has_complete_timing is True


def test_landed_flight_is_complete() -> None:
    assert facts().has_complete_timing is True


# --- Normalisation and validation --------------------------------------------


def test_codes_are_normalised_at_the_boundary() -> None:
    """So no rule ever has to wonder whether "tlv" equals "TLV"."""
    f = facts(origin_iata=" tlv ", airline_country="gb", destination_iata="lhr")
    assert (f.origin_iata, f.airline_country, f.destination_iata) == ("TLV", "GB", "LHR")


def test_negative_distance_is_rejected() -> None:
    with pytest.raises(ValueError, match="distance_km"):
        facts(distance_km=-1.0)


def test_facts_are_immutable() -> None:
    """A snapshot of what happened, not a mutable working copy."""
    with pytest.raises(AttributeError):
        facts().distance_km = 99.0  # type: ignore[misc]


# --- Verdict -----------------------------------------------------------------


def test_verdict_has_exactly_three_values() -> None:
    """Guards the decision itself.

    If someone later "simplifies" this to a boolean, the NEEDS_REVIEW safety net
    disappears and failed lookups start silently becoming NOT_ELIGIBLE.
    """
    assert set(Verdict) == {Verdict.ELIGIBLE, Verdict.NOT_ELIGIBLE, Verdict.NEEDS_REVIEW}
