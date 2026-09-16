"""Tests for UK261.

UK261 shares its flow with EC261 through `base.ArrivalDelayRegulation`, and
test_ec261.py already exercises that flow hard -- thresholds, band boundaries,
the long-haul reduction, and every NEEDS_REVIEW path. Repeating all of it here
would triple the suite without testing anything new.

So this file concentrates on what is genuinely different about UK261:

  1. Its jurisdiction, which is NOT a copy of EC261's -- EU carriers count for
     arrivals into the UK, but EU airports do not
  2. Its money: pounds, not euros, and different figures
  3. The Crown Dependencies and Gibraltar, which are unsettled
  4. Enough of the shared flow to prove this law is actually wired to it
"""

import pytest

from app.domain.models import Currency, FlightStatus, Money, Verdict
from app.domain.rules import ec261, uk261
from tests.unit.builders import a_flight

GBP = Currency.GBP


# --- 1. Jurisdiction ---------------------------------------------------------


def test_departing_the_uk_covers_any_airline() -> None:
    """El Al out of Heathrow is covered, because the flight leaves the UK."""
    flight = a_flight(
        airline="LY", airline_country="IL",
        origin="LHR", origin_country="GB",
        destination="TLV", destination_country="IL",
    )
    assert uk261.applies(flight) is True


def test_arriving_in_the_uk_on_a_uk_carrier_is_covered() -> None:
    flight = a_flight(
        airline="BA", airline_country="GB",
        origin="TLV", origin_country="IL",
        destination="LHR", destination_country="GB",
    )
    assert uk261.applies(flight) is True


def test_arriving_in_the_uk_on_an_eu_carrier_is_covered() -> None:
    """The detail that makes UK261's jurisdiction wider than a find-and-replace
    of EC261's.

    The retained regulation kept EU-licensed carriers inside the arrivals rule,
    so Lufthansa flying Tel Aviv -> London is covered even though Lufthansa is
    not British. Copying EC261's "own carriers only" logic would wrongly exclude
    every EU airline arriving into the UK.
    """
    flight = a_flight(
        airline="LH", airline_country="DE",
        origin="TLV", origin_country="IL",
        destination="LHR", destination_country="GB",
    )
    assert uk261.applies(flight) is True


def test_arriving_in_the_uk_on_a_non_uk_non_eu_carrier_is_not_covered() -> None:
    """The boundary of the rule above. El Al arriving into Heathrow is not
    covered -- Israel is neither the UK nor the EU."""
    flight = a_flight(
        airline="LY", airline_country="IL",
        origin="TLV", origin_country="IL",
        destination="LHR", destination_country="GB",
    )
    assert uk261.applies(flight) is False


def test_departing_the_eu_does_not_trigger_uk261() -> None:
    """Brexit, in one test.

    Paris -> Madrid is squarely inside EC261 and has nothing to do with UK261.
    If the UK territory set had been copied from the EU one, every intra-EU
    flight would wrongly produce a pounds-denominated award.
    """
    flight = a_flight(
        airline="AF", airline_country="FR",
        origin="CDG", origin_country="FR",
        destination="MAD", destination_country="ES",
    )
    assert uk261.applies(flight) is False
    assert ec261.applies(flight) is True


def test_a_flight_can_be_covered_by_both_regulations() -> None:
    """Dublin -> London: departs the EU *and* arrives in the UK on an EU carrier.

    Both laws apply. The engine in step 9 has to present both and rank them;
    this test pins the fact that the situation is real rather than theoretical.
    """
    flight = a_flight(
        airline="EI", airline_country="IE",
        origin="DUB", origin_country="IE",
        destination="LHR", destination_country="GB",
    )
    assert ec261.applies(flight) is True
    assert uk261.applies(flight) is True


# --- 2. The money ------------------------------------------------------------


@pytest.mark.parametrize(
    ("distance", "expected"),
    [
        (1.0, "220"),
        (1500.0, "220"),    # "1,500 km or less" -- inclusive
        (1500.1, "350"),
        (3500.0, "350"),    # inclusive again
        (3500.1, "520"),
        (9000.0, "520"),
    ],
)
def test_distance_bands_pay_pounds(distance: float, expected: str) -> None:
    """The boundaries are shared code, but the figures are not.

    Tested here because a transcription slip -- 350 typed as 250, or the euro
    figures pasted in wholesale -- is exactly the kind of error a shared flow
    cannot catch for you.
    """
    outcome = uk261.evaluate(
        a_flight(origin_country="GB", distance_km=distance, arrival_delay_hours=5.0)
    )
    assert outcome.award == Money.of(expected, GBP)


def test_awards_are_in_pounds_not_euros() -> None:
    """A currency mix-up would be invisible in the amount alone."""
    outcome = uk261.evaluate(a_flight(origin_country="GB", arrival_delay_hours=5.0))
    assert outcome.award is not None
    assert outcome.award.currency is Currency.GBP
    assert "£" in str(outcome.award)


def test_long_haul_always_pays_in_full() -> None:
    """No reduction here either -- the retained Article 7(2) carries the same
    re-routing precondition, so it does not reach delay claims."""
    for delay in (3.0, 3.5, 4.0, 6.0):
        outcome = uk261.evaluate(
            a_flight(origin_country="GB", distance_km=5000.0, arrival_delay_hours=delay)
        )
        assert outcome.award == Money.of("520", GBP)


def test_the_two_regulations_pay_different_amounts_for_the_same_flight() -> None:
    """Dublin -> London, 4 hours late, 465 km.

    EC261 pays 250 euro and UK261 pays 220 pounds for the identical flight.
    Proves the two laws are wired to their own constants and not accidentally
    sharing a single table.
    """
    flight = a_flight(
        airline="EI", airline_country="IE",
        origin="DUB", origin_country="IE",
        destination="LHR", destination_country="GB",
        distance_km=465.0, arrival_delay_hours=4.0,
    )
    assert ec261.evaluate(flight).award == Money.of("250", Currency.EUR)
    assert uk261.evaluate(flight).award == Money.of("220", Currency.GBP)


# --- 3. Gibraltar and the Crown Dependencies ---------------------------------


@pytest.mark.parametrize(
    ("country", "place"),
    [("GI", "Gibraltar"), ("JE", "Jersey"), ("GG", "Guernsey"), ("IM", "Isle of Man")],
)
def test_unsettled_territories_go_to_review(country: str, place: str) -> None:
    """None of these is part of the United Kingdom.

    Whether the retained regulation reaches them is genuinely unsettled, not
    merely unresearched. Returning NOT_ELIGIBLE would be a confident answer we
    have not earned -- and per the standing rule, a wrong "no" is the expensive
    one, because the passenger closes the tab and nobody ever finds out.
    """
    outcome = uk261.evaluate(
        a_flight(origin_country=country, destination_country="GB",
                 airline_country="GB", arrival_delay_hours=5.0)
    )
    assert outcome.verdict is Verdict.NEEDS_REVIEW
    assert country in outcome.reason, place


def test_unsettled_territory_is_flagged_even_at_the_destination() -> None:
    """The check looks at both ends of the route, not just the origin."""
    outcome = uk261.evaluate(
        a_flight(origin_country="GB", destination_country="JE",
                 airline_country="GB", arrival_delay_hours=5.0)
    )
    assert outcome.verdict is Verdict.NEEDS_REVIEW


def test_unsettled_territories_do_not_affect_ec261() -> None:
    """Jersey is not a UK261 question for EC261 to worry about.

    A Paris -> Jersey flight departs the EU, so EC261 answers confidently. Only
    UK261 has a Crown Dependency problem, and the flag must not leak.
    """
    flight = a_flight(
        airline="AF", airline_country="FR",
        origin="CDG", origin_country="FR",
        destination="JER", destination_country="JE",
        distance_km=500.0, arrival_delay_hours=5.0,
    )
    assert ec261.evaluate(flight).verdict is Verdict.ELIGIBLE
    assert uk261.evaluate(flight).verdict is Verdict.NEEDS_REVIEW


# --- 4. Proof this law is actually wired to the shared flow ------------------
#
# Smoke tests, not a second copy of the EC261 suite. Each confirms one branch of
# the shared machinery reaches UK261 with UK wording.


@pytest.mark.parametrize(
    ("delay", "expected"),
    [(2.9833, Verdict.NOT_ELIGIBLE), (3.0, Verdict.ELIGIBLE)],
)
def test_the_three_hour_threshold_applies(delay: float, expected: Verdict) -> None:
    outcome = uk261.evaluate(a_flight(origin_country="GB", arrival_delay_hours=delay))
    assert outcome.verdict is expected


def test_cancelled_flights_need_review() -> None:
    outcome = uk261.evaluate(
        a_flight(origin_country="GB", status=FlightStatus.CANCELLED,
                 arrival_delay_hours=None)
    )
    assert outcome.verdict is Verdict.NEEDS_REVIEW
    assert "14 days" in outcome.reason


def test_departure_delay_is_irrelevant() -> None:
    """Left 9 hours late, landed 2 hours late: nothing owed."""
    outcome = uk261.evaluate(
        a_flight(origin_country="GB", departure_delay_hours=9.0, arrival_delay_hours=2.0)
    )
    assert outcome.verdict is Verdict.NOT_ELIGIBLE


def test_reasons_name_uk261_and_not_ec261() -> None:
    """The reason string is shown to the customer, so it must name the right law.

    A copy-paste slip in a shared reason template would tell a British claimant
    they are covered by an EU regulation.
    """
    for flight in (
        a_flight(origin_country="GB", arrival_delay_hours=5.0),      # eligible
        a_flight(origin_country="GB", arrival_delay_hours=1.0),      # not eligible
        a_flight(origin_country="IL", destination_country="US",      # out of scope
                 airline_country="IL"),
    ):
        reason = uk261.evaluate(flight).reason
        assert "UK261" in reason
        assert "EC261" not in reason


# --- 5. The worked examples from rules.md ------------------------------------


def test_rules_md_examples_a_and_b_tel_aviv_to_london() -> None:
    """TLV -> LHR on British Airways, 3,589 km, 4 hours late -> 520 pounds.

    This is the headline example in rules.md, and the one the whole project
    started from.
    """
    outcome = uk261.evaluate(
        a_flight(
            flight_number="BA165", airline="BA", airline_country="GB",
            origin="TLV", origin_country="IL",
            destination="LHR", destination_country="GB",
            distance_km=3588.6, arrival_delay_hours=4.0,
        )
    )
    assert outcome.verdict is Verdict.ELIGIBLE
    assert outcome.award == Money.of("520", GBP)
