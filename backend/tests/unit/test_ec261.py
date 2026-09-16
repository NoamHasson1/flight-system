"""Tests for EC261.

This is the file where a bug costs real money, so the cases are chosen around
boundaries and around the specific mistakes this regulation invites.

Groups:
  1. Jurisdiction -- the asymmetric "departing vs arriving" rule
  2. Territories  -- outermost regions in, overseas territories out
  3. The 3-hour threshold, tested either side of the boundary
  4. Distance bands, tested either side of both boundaries
  5. The Article 7(2) long-haul reduction
  6. Everything that must become NEEDS_REVIEW rather than a confident "no"
  7. The worked examples from rules.md
"""

from decimal import Decimal

import pytest

from app.domain.models import Currency, FlightStatus, Money, Verdict
from app.domain.rules import ec261
from app.domain.rules.base import RegulationOutcome
from tests.unit.builders import a_flight

EUR = Currency.EUR


# --- 1. Jurisdiction ---------------------------------------------------------


def test_departing_the_eu_covers_any_airline() -> None:
    """The half people remember. Departure from the EU covers everyone.

    El Al is Israeli, but this flight leaves France, so EC261 applies.
    """
    flight = a_flight(
        airline="LY", airline_country="IL",
        origin="CDG", origin_country="FR",
        destination="TLV", destination_country="IL",
    )
    assert ec261.applies(flight) is True


def test_arriving_in_the_eu_only_covers_eu_carriers() -> None:
    """The half people forget, and the reason this test exists.

    Same airline, same two airports, opposite direction. Now the flight only
    *arrives* into the EU, and El Al is not a Community carrier -- so EC261 does
    not apply. An implementation that checked "is either endpoint in the EU?"
    would wrongly pay this passenger 400 euro.
    """
    flight = a_flight(
        airline="LY", airline_country="IL",
        origin="TLV", origin_country="IL",
        destination="CDG", destination_country="FR",
    )
    assert ec261.applies(flight) is False


def test_arriving_in_the_eu_on_an_eu_carrier_is_covered() -> None:
    """The mirror of the test above: swap the airline and it flips to covered."""
    flight = a_flight(
        airline="AF", airline_country="FR",
        origin="TLV", origin_country="IL",
        destination="CDG", destination_country="FR",
    )
    assert ec261.applies(flight) is True


def test_wholly_outside_the_eu_is_not_covered() -> None:
    flight = a_flight(
        airline="LY", airline_country="IL",
        origin="TLV", origin_country="IL",
        destination="JFK", destination_country="US",
    )
    assert ec261.applies(flight) is False


def test_ryanair_counts_as_an_eu_carrier() -> None:
    """Ryanair is Irish. Filing it as British would silently exclude every
    Ryanair flight arriving into the EU from outside it."""
    flight = a_flight(
        airline="FR", airline_country="IE",
        origin="TLV", origin_country="IL",
        destination="DUB", destination_country="IE",
    )
    assert ec261.applies(flight) is True


# --- 2. Territories ----------------------------------------------------------


@pytest.mark.parametrize(
    ("country", "place"),
    [("GP", "Guadeloupe"), ("MQ", "Martinique"), ("GF", "French Guiana"),
     ("RE", "Reunion"), ("YT", "Mayotte"), ("MF", "Saint-Martin")],
)
def test_eu_outermost_regions_are_covered(country: str, place: str) -> None:
    """These are legally part of the EU but have their own ISO codes.

    A naive `country in EU_27` check silently excludes every flight from
    Martinique or Reunion -- real routes with real passengers.
    """
    flight = a_flight(airline="LY", airline_country="IL",
                      origin="XXX", origin_country=country)
    assert ec261.applies(flight) is True, f"{place} is an EU outermost region"


@pytest.mark.parametrize(
    ("country", "place"),
    [("NC", "New Caledonia"), ("PF", "French Polynesia"), ("BL", "Saint-Barthelemy"),
     ("PM", "Saint-Pierre-et-Miquelon"), ("GL", "Greenland"), ("FO", "Faroe Islands"),
     ("AW", "Aruba"), ("CW", "Curacao")],
)
def test_overseas_territories_are_not_covered(country: str, place: str) -> None:
    """Associated with the EU, but outside it. The counterpart to the test
    above: getting this wrong in the other direction promises money that is
    not owed."""
    flight = a_flight(airline="LY", airline_country="IL",
                      origin="XXX", origin_country=country,
                      destination="YYY", destination_country="US")
    assert ec261.applies(flight) is False, f"{place} is an OCT, not part of the EU"


def test_eea_states_are_covered() -> None:
    """Norway and Iceland are not in the EU but EC261 applies there."""
    for country in ("NO", "IS"):
        flight = a_flight(airline="LY", airline_country="IL",
                          origin="XXX", origin_country=country)
        assert ec261.applies(flight) is True


def test_switzerland_is_covered_by_the_bilateral_agreement() -> None:
    """Switzerland is in neither the EU nor the EEA, but applies EC261 through
    its air transport agreement with the EU."""
    flight = a_flight(airline="LY", airline_country="IL",
                      origin="ZRH", origin_country="CH")
    assert ec261.applies(flight) is True


# --- 3. The three-hour threshold ---------------------------------------------


@pytest.mark.parametrize(
    ("delay", "expected"),
    [
        (2.9833, Verdict.NOT_ELIGIBLE),   # 2h 59m
        (3.0, Verdict.ELIGIBLE),          # exactly 3h -- "three hours or more"
        (3.0167, Verdict.ELIGIBLE),       # 3h 01m
    ],
)
def test_the_three_hour_boundary(delay: float, expected: Verdict) -> None:
    """The single most important threshold in the regulation.

    Tested at 2h59, exactly 3h and 3h01 because the difference between `>` and
    `>=` at exactly three hours is the difference between 0 and 600 euro, and
    it is invisible in any test that only checks 2h and 5h.
    """
    outcome = ec261.evaluate(a_flight(origin_country="FR", arrival_delay_hours=delay))
    assert outcome.verdict is expected


def test_a_short_delay_explains_itself() -> None:
    """A "no" must say why. This reason string is shown to the customer."""
    outcome = ec261.evaluate(a_flight(origin_country="FR", arrival_delay_hours=1.5))
    assert outcome.applies is True
    assert "1h 30m" in outcome.reason
    assert "3h 00m threshold" in outcome.reason


def test_departure_delay_is_irrelevant_to_ec261() -> None:
    """The classic mistake, pinned.

    Pushed back 9 hours late, landed 2 hours late because the pilot made up
    time. EC261 measures at arrival, so this passenger gets nothing. An
    implementation reading departure delay would pay out 600 euro.
    """
    flight = a_flight(
        origin_country="FR", departure_delay_hours=9.0, arrival_delay_hours=2.0
    )
    outcome = ec261.evaluate(flight)
    assert outcome.verdict is Verdict.NOT_ELIGIBLE
    assert flight.departure_delay_hours == 9.0


# --- 4. Distance bands -------------------------------------------------------


@pytest.mark.parametrize(
    ("distance", "expected"),
    [
        (1.0, "250"),
        (1499.0, "250"),
        (1500.0, "250"),     # "1,500 km or less" -- inclusive
        (1500.1, "400"),
        (3499.0, "400"),
        (3500.0, "400"),     # inclusive again
        (3500.1, "600"),
        (12000.0, "600"),
    ],
)
def test_distance_bands(distance: float, expected: str) -> None:
    """Both boundaries, from both sides.

    The regulation says "1,500 kilometres or less", so 1,500.0 belongs to the
    lower band. An off-by-one here underpays by 150 euro on every affected
    flight, forever, and nothing else would ever reveal it.
    """
    # 5 hours keeps us clear of the long-haul reduction window.
    outcome = ec261.evaluate(
        a_flight(origin_country="FR", distance_km=distance, arrival_delay_hours=5.0)
    )
    assert outcome.award == Money.of(expected, EUR)


# --- 5. The Article 7(2) long-haul reduction ---------------------------------


@pytest.mark.parametrize(
    ("delay", "expected", "note"),
    [
        (3.0, "300", "3h on a long haul -- halved"),
        (3.9833, "300", "3h 59m -- still halved"),
        (4.0, "600", "exactly 4h -- no longer 'within four hours'"),
        (6.0, "600", "well past 4h -- full amount"),
    ],
)
def test_long_haul_reduction_window(delay: float, expected: str, note: str) -> None:
    """Article 7(2)(c): half the amount if the airline lands you inside 4 hours.

    This only bites on flights over 3,500 km, in the narrow band between 3 and
    4 hours. Tested on both sides of the 4-hour edge.
    """
    outcome = ec261.evaluate(
        a_flight(origin_country="FR", distance_km=5000.0, arrival_delay_hours=delay)
    )
    assert outcome.award == Money.of(expected, EUR), note


def test_reduction_does_not_apply_to_shorter_flights() -> None:
    """A 3h delay on a 2,000 km flight pays the full 400 euro."""
    outcome = ec261.evaluate(
        a_flight(origin_country="FR", distance_km=2000.0, arrival_delay_hours=3.0)
    )
    assert outcome.award == Money.of("400", EUR)


def test_the_reduction_is_explained() -> None:
    outcome = ec261.evaluate(
        a_flight(origin_country="FR", distance_km=5000.0, arrival_delay_hours=3.5)
    )
    assert "halved" in outcome.reason
    assert "€600.00" in outcome.reason and "€300.00" in outcome.reason


# --- 6. Everything that must become NEEDS_REVIEW ------------------------------
#
# This group is the safety net. Each case is one where a naive implementation
# would return NOT_ELIGIBLE -- a wrong "no" that costs the passenger money and
# that nobody ever discovers, because they just close the tab.


def test_cancelled_flights_need_review_not_a_verdict() -> None:
    """Cancellation compensation depends on how much notice the passenger got.

    Under 14 days and it is payable. No flight API reports that, so we must ask.
    Guessing "eligible" over-promises; guessing "not eligible" is the expensive
    silent error.
    """
    outcome = ec261.evaluate(
        a_flight(origin_country="FR", status=FlightStatus.CANCELLED,
                 arrival_delay_hours=None)
    )
    assert outcome.verdict is Verdict.NEEDS_REVIEW
    assert "14 days" in outcome.reason


def test_a_flight_with_no_arrival_time_needs_review() -> None:
    """Still airborne, or the provider simply did not say.

    Treating a missing arrival time as a zero delay would confidently tell a
    passenger mid-flight that they have no claim.
    """
    outcome = ec261.evaluate(a_flight(origin_country="FR", arrival_delay_hours=None,
                                      status=FlightStatus.EN_ROUTE))
    assert outcome.verdict is Verdict.NEEDS_REVIEW


def test_diverted_flights_need_review() -> None:
    """The passenger landed somewhere else entirely. The compensation question
    becomes 'where was the final destination', which needs a person."""
    outcome = ec261.evaluate(
        a_flight(origin_country="FR", status=FlightStatus.DIVERTED)
    )
    assert outcome.verdict is Verdict.NEEDS_REVIEW


def test_unknown_status_needs_review() -> None:
    """The provider told us something we do not recognise. Say so."""
    outcome = ec261.evaluate(a_flight(origin_country="FR", status=FlightStatus.UNKNOWN))
    assert outcome.verdict is Verdict.NEEDS_REVIEW


def test_review_outcomes_still_record_that_the_law_applies() -> None:
    """NEEDS_REVIEW is about the facts, not about jurisdiction.

    The engine needs to know this law covered the flight so it can tell the
    customer which regulation the outstanding question belongs to.
    """
    outcome = ec261.evaluate(
        a_flight(origin_country="FR", status=FlightStatus.DIVERTED)
    )
    assert outcome.applies is True


def test_out_of_scope_flights_are_not_eligible_rather_than_review() -> None:
    """A flight EC261 simply does not cover is a confident, complete answer.

    Sending it to manual review would bury every genuine question in noise.
    """
    outcome = ec261.evaluate(
        a_flight(origin_country="IL", destination_country="US",
                 airline_country="IL")
    )
    assert outcome.verdict is Verdict.NOT_ELIGIBLE
    assert outcome.applies is False


# --- 7. The worked examples from rules.md ------------------------------------


def test_rules_md_example_c_paris_to_tel_aviv_on_el_al() -> None:
    """Example C: CDG -> TLV on El Al, 3.5 hours late, 3,290 km -> 400 euro.

    Keeping the documented examples as executable tests means rules.md cannot
    quietly drift away from the code.
    """
    outcome = ec261.evaluate(
        a_flight(
            flight_number="LY324", airline="LY", airline_country="IL",
            origin="CDG", origin_country="FR",
            destination="TLV", destination_country="IL",
            distance_km=3290.0, arrival_delay_hours=3.5,
        )
    )
    assert outcome.verdict is Verdict.ELIGIBLE
    assert outcome.award == Money.of("400", EUR)


def test_rules_md_example_a_tel_aviv_to_london() -> None:
    """Examples A and B: TLV -> LHR is outside EC261 entirely."""
    outcome = ec261.evaluate(
        a_flight(airline="BA", airline_country="GB",
                 origin="TLV", origin_country="IL",
                 destination="LHR", destination_country="GB")
    )
    assert outcome.verdict is Verdict.NOT_ELIGIBLE
    assert outcome.applies is False


# --- The outcome type's own invariants ---------------------------------------


def test_eligible_outcome_must_carry_an_award() -> None:
    """Structural guard. An ELIGIBLE with no amount would render as "you are
    owed None" somewhere downstream."""
    with pytest.raises(ValueError, match="must carry an award"):
        RegulationOutcome(regulation="EC261", verdict=Verdict.ELIGIBLE,
                          reason="x", applies=True, award=None)


def test_non_eligible_outcome_must_not_carry_an_award() -> None:
    """The mirror. A NOT_ELIGIBLE carrying 600 euro is a bug waiting to be
    displayed to a customer."""
    with pytest.raises(ValueError, match="only an ELIGIBLE"):
        RegulationOutcome(regulation="EC261", verdict=Verdict.NOT_ELIGIBLE,
                          reason="x", applies=False,
                          award=Money(Decimal("600.00"), EUR))
