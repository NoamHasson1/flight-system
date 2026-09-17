"""Tests for the Israeli Aviation Services Law (the Tibi Law).

This law does not share EC261's flow, so unlike test_uk261.py this file has to
cover everything itself. It concentrates hardest on the four places where the
Israeli rules differ from the European ones, because those differences are
exactly what a copy-paste from ec261.py would destroy:

  1. Delay measured at DEPARTURE, not arrival
  2. An 8-hour threshold, not 3
  3. Bands at 2,000 / 4,500 km, not 1,500 / 3,500
  4. A 50% reduction that is real, and keyed to the ARRIVAL delay
"""

import pytest

from app.domain.models import Currency, FlightStatus, Money, Verdict
from app.domain.rules import ec261, israel, uk261
from tests.unit.builders import a_flight

ILS = Currency.ILS


# --- 1. Jurisdiction ---------------------------------------------------------


@pytest.mark.parametrize(
    ("origin", "destination"), [("IL", "GB"), ("GB", "IL"), ("IL", "US")]
)
def test_either_end_in_israel_is_covered(origin: str, destination: str) -> None:
    """Simpler than EC261 and UK261: no carrier-nationality test at all.

    Any airline, in either direction, so long as one end is Israel.
    """
    flight = a_flight(origin_country=origin, destination_country=destination)
    assert israel.applies(flight) is True


def test_carrier_nationality_is_irrelevant() -> None:
    """The distinction that decides EC261 and UK261 has no effect here.

    El Al and British Airways on the same route get the same answer. Copying
    the European jurisdiction logic across would wrongly introduce a carrier
    test this law does not have.
    """
    for carrier_country in ("IL", "GB", "US", "TR"):
        flight = a_flight(origin_country="IL", airline_country=carrier_country)
        assert israel.applies(flight) is True


def test_flights_nowhere_near_israel_are_not_covered() -> None:
    flight = a_flight(origin_country="FR", destination_country="US")
    assert israel.applies(flight) is False


# --- 2. The eight-hour threshold, measured at DEPARTURE ----------------------


@pytest.mark.parametrize(
    ("delay", "expected"),
    [
        (7.9833, Verdict.NOT_ELIGIBLE),  # 7h 59m
        (8.0, Verdict.ELIGIBLE),         # exactly 8h -- "8 hours or more"
        (8.0167, Verdict.ELIGIBLE),      # 8h 01m
    ],
)
def test_the_eight_hour_boundary(delay: float, expected: Verdict) -> None:
    """Israel's threshold is nearly three times Europe's, and it is its own
    boundary to get wrong."""
    outcome = israel.evaluate(
        a_flight(origin_country="IL", departure_delay_hours=delay,
                 arrival_delay_hours=delay)
    )
    assert outcome.verdict is expected


def test_the_threshold_reads_departure_delay_not_arrival() -> None:
    """The single most important test in this file.

    Departed 9 hours late, and the pilot made up so much time it landed only
    1 hour late. Under EC261 and UK261 that passenger gets nothing -- those laws
    measure at arrival. Under Israeli law they are eligible, because it measures
    at departure.

    An implementation that copied the European logic would return NOT_ELIGIBLE
    here: a wrong "no" on a real, substantial claim.
    """
    flight = a_flight(
        origin_country="IL", distance_km=3588.6,
        departure_delay_hours=9.0, arrival_delay_hours=1.0,
    )
    assert israel.evaluate(flight).verdict is Verdict.ELIGIBLE
    assert ec261.evaluate(flight).verdict is Verdict.NOT_ELIGIBLE
    assert uk261.evaluate(flight).verdict is Verdict.NOT_ELIGIBLE


def test_the_mirror_case_a_long_arrival_delay_is_not_enough() -> None:
    """The other direction: left 2 hours late, landed 9 hours late.

    Europe pays. Israel does not, because the departure delay is what counts.
    """
    flight = a_flight(
        origin_country="IL", destination_country="GB", airline_country="GB",
        distance_km=3588.6, departure_delay_hours=2.0, arrival_delay_hours=9.0,
    )
    assert israel.evaluate(flight).verdict is Verdict.NOT_ELIGIBLE
    assert uk261.evaluate(flight).verdict is Verdict.ELIGIBLE


def test_a_short_delay_explains_which_clock_was_used() -> None:
    """The reason must say the delay was measured at departure.

    Otherwise a passenger who arrived 5 hours late reads "you departed 2h late,
    below the threshold" and thinks we misread their flight.
    """
    outcome = israel.evaluate(
        a_flight(origin_country="IL", departure_delay_hours=2.0,
                 arrival_delay_hours=5.0)
    )
    assert "at departure, not at arrival" in outcome.reason


# --- 3. Distance bands: 2,000 and 4,500 km, not 1,500 and 3,500 --------------


@pytest.mark.parametrize(
    ("distance", "expected"),
    [
        (1.0, "1530"),
        (1999.0, "1530"),
        (2000.0, "1530"),    # "2,000 km or less" -- inclusive
        (2000.1, "2450"),
        (4499.0, "2450"),
        (4500.0, "2450"),    # inclusive again
        (4500.1, "3670"),
        (12000.0, "3670"),
    ],
)
def test_distance_bands(distance: float, expected: str) -> None:
    """Both Israeli boundaries, from both sides.

    A 10-hour arrival delay keeps every case clear of the reduction window.
    """
    outcome = israel.evaluate(
        a_flight(origin_country="IL", distance_km=distance,
                 departure_delay_hours=10.0, arrival_delay_hours=10.0)
    )
    assert outcome.award == Money.of(expected, ILS)


def test_the_bands_are_not_the_european_ones() -> None:
    """A 3,000 km flight sits in different bands under different laws.

    Under EC261 it is in the top-but-one band; under Israeli law it is also the
    middle band but split at completely different boundaries. This test pins a
    distance where copying 1,500/3,500 into this file would change the answer:
    at 1,800 km the European bands say "band 1" while the Israeli bands say
    "band 0".
    """
    outcome = israel.evaluate(
        a_flight(origin_country="IL", distance_km=1800.0,
                 departure_delay_hours=10.0, arrival_delay_hours=10.0)
    )
    assert outcome.award == Money.of("1530", ILS)  # not the middle band


# --- 4. The 50% reduction, keyed to the ARRIVAL delay ------------------------


@pytest.mark.parametrize(
    ("distance", "arrival_delay", "expected", "note"),
    [
        (1500.0, 4.0, "765", "band 0, exactly 4h -- 'does not exceed' is inclusive"),
        (1500.0, 4.0167, "1530", "band 0, 4h 01m -- full amount"),
        (3000.0, 5.0, "1225", "band 1, exactly 5h -- halved"),
        (3000.0, 5.0167, "2450", "band 1, 5h 01m -- full"),
        (6000.0, 6.0, "1835", "band 2, exactly 6h -- halved"),
        (6000.0, 6.0167, "3670", "band 2, 6h 01m -- full"),
    ],
)
def test_the_reduction_ceiling_widens_with_distance(
    distance: float, arrival_delay: float, expected: str, note: str
) -> None:
    """Three different ceilings -- 4h, 5h and 6h -- one per band.

    This is the most intricate rule in the whole system: eligibility is decided
    on the departure delay, but the amount is decided on the arrival delay,
    against a ceiling that depends on the distance. Every boundary is tested
    from both sides because there is no simpler way to be sure.
    """
    outcome = israel.evaluate(
        a_flight(origin_country="IL", distance_km=distance,
                 departure_delay_hours=10.0, arrival_delay_hours=arrival_delay)
    )
    assert outcome.award == Money.of(expected, ILS), note


def test_all_three_halved_amounts_are_exact() -> None:
    """1530, 2450 and 3670 all halve without a fraction of an agora."""
    assert Money.of("1530", ILS).halved() == Money.of("765", ILS)
    assert Money.of("2450", ILS).halved() == Money.of("1225", ILS)
    assert Money.of("3670", ILS).halved() == Money.of("1835", ILS)


def test_the_reduction_is_explained_with_both_numbers() -> None:
    """The customer sees why they are getting half."""
    outcome = israel.evaluate(
        a_flight(origin_country="IL", distance_km=3000.0,
                 departure_delay_hours=10.0, arrival_delay_hours=4.0)
    )
    assert "halved" in outcome.reason
    assert "₪2,450.00" in outcome.reason and "₪1,225.00" in outcome.reason
    assert "5h 00m" in outcome.reason  # the ceiling for this band


def test_europe_has_no_such_reduction() -> None:
    """The counterpart to the Israeli rule.

    EC261's Article 7(2) reduction is about re-routing after a cancellation, so
    it does not reach delay claims and we do not apply it. The Israeli one is
    written into the delay provision itself. Pinning both here stops the two
    from being "harmonised" later by someone who notices they look similar.
    """
    flight = a_flight(origin_country="FR", distance_km=6000.0,
                      departure_delay_hours=3.5, arrival_delay_hours=3.5)
    assert ec261.evaluate(flight).award == Money.of("600", Currency.EUR)


# --- Everything that must become NEEDS_REVIEW --------------------------------


def test_cancelled_flights_need_review() -> None:
    outcome = israel.evaluate(
        a_flight(origin_country="IL", status=FlightStatus.CANCELLED,
                 arrival_delay_hours=None, departure_delay_hours=None)
    )
    assert outcome.verdict is Verdict.NEEDS_REVIEW
    assert "14 days" in outcome.reason


def test_no_departure_time_needs_review() -> None:
    outcome = israel.evaluate(
        a_flight(origin_country="IL", status=FlightStatus.SCHEDULED,
                 departure_delay_hours=None, arrival_delay_hours=None)
    )
    assert outcome.verdict is Verdict.NEEDS_REVIEW


def test_qualifying_departure_delay_but_no_arrival_time_needs_review() -> None:
    """A case unique to this law, and a genuinely awkward one.

    The departure delay already proves the passenger is eligible -- but the
    amount depends on the arrival delay, which we do not have. We can say "yes"
    and not "how much".

    Guessing the full amount over-promises; guessing the halved amount
    under-promises; NOT_ELIGIBLE would be flatly wrong. So it goes to a person,
    and the reason says the departure delay qualified.
    """
    outcome = israel.evaluate(
        a_flight(origin_country="IL", status=FlightStatus.EN_ROUTE,
                 departure_delay_hours=9.0, arrival_delay_hours=None)
    )
    assert outcome.verdict is Verdict.NEEDS_REVIEW
    assert "9h 00m" in outcome.reason
    assert "qualifies" in outcome.reason


def test_diverted_and_unknown_need_review() -> None:
    for status in (FlightStatus.DIVERTED, FlightStatus.UNKNOWN):
        outcome = israel.evaluate(a_flight(origin_country="IL", status=status))
        assert outcome.verdict is Verdict.NEEDS_REVIEW


def test_flights_outside_israel_are_not_eligible_rather_than_review() -> None:
    outcome = israel.evaluate(
        a_flight(origin_country="FR", destination_country="US")
    )
    assert outcome.verdict is Verdict.NOT_ELIGIBLE
    assert outcome.applies is False


# --- The worked examples from rules.md ---------------------------------------


def test_rules_md_example_a_four_hours_is_not_enough() -> None:
    """Example A: TLV -> LHR, 4 hours late. Israel pays nothing."""
    outcome = israel.evaluate(
        a_flight(origin_country="IL", destination_country="GB",
                 distance_km=3588.6, departure_delay_hours=4.0,
                 arrival_delay_hours=4.0)
    )
    assert outcome.verdict is Verdict.NOT_ELIGIBLE
    assert outcome.applies is True


def test_rules_md_example_b_nine_hours_pays_2450() -> None:
    """Example B: TLV -> LHR, 9 hours late, 3,589 km.

    In the 2,000-4,500 km band, and the 9-hour arrival delay is well past the
    5-hour ceiling, so no reduction: the full 2,450 shekels.
    """
    outcome = israel.evaluate(
        a_flight(flight_number="BA165", airline="BA", airline_country="GB",
                 origin="TLV", origin_country="IL",
                 destination="LHR", destination_country="GB",
                 distance_km=3588.6, departure_delay_hours=9.0,
                 arrival_delay_hours=9.0)
    )
    assert outcome.verdict is Verdict.ELIGIBLE
    assert outcome.award == Money.of("2450", ILS)


def test_rules_md_example_d_tel_aviv_to_new_york_two_hours() -> None:
    """Example D: covered by the law, but nowhere near the threshold."""
    outcome = israel.evaluate(
        a_flight(origin_country="IL", destination_country="US",
                 distance_km=9117.0, departure_delay_hours=2.0,
                 arrival_delay_hours=2.0)
    )
    assert outcome.verdict is Verdict.NOT_ELIGIBLE
    assert outcome.applies is True
    assert "8h 00m threshold" in outcome.reason


def test_the_israeli_law_has_no_measurement_margin() -> None:
    """EC261 and UK261 decline to decide within fifteen minutes of their
    threshold, because Germanwings put "arrival" at the moment a door opens
    while flight databases record touchdown.

    The Israeli law has no such gap. It triggers on the DEPARTURE delay, and its
    reduction keys off the "landing time" -- which is touchdown, exactly what we
    measure. There is nothing to be uncertain about, so 7h 50m is a straight no.
    """
    outcome = israel.evaluate(
        a_flight(origin_country="IL", departure_delay_hours=7.8333,
                 arrival_delay_hours=7.8333)
    )
    assert outcome.verdict is Verdict.NOT_ELIGIBLE
    assert "7h 50m" in outcome.reason
