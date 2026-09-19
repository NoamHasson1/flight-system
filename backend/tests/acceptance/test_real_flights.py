"""Acceptance tests: real airlines, real routes, hand-derived expectations.

Every case below is a flight that genuinely operates, with distances taken from
the shipped airport dataset and carrier nationalities from the shipped airline
file. The delays are scenarios rather than recorded history -- no flight data
subscription exists yet -- but everything else is real.

**The expectations were worked out by hand from rules.md before the code was
run.** That is the whole point. A test written by running the system and
recording what it said proves only that the system is consistent with itself;
these say what the law requires and let the code disagree.

Each case carries the reasoning that produced its expectation, so a future
reader can check the working rather than trust it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

import pytest

from app.domain.models import FlightFacts, FlightStatus, Verdict
from app.domain.reference import distance_between, find_airline, find_airport
from app.domain.rules import engine

SCHEDULED_DEPARTURE = datetime(2026, 8, 14, 10, 0, tzinfo=UTC)
SCHEDULED_ARRIVAL = datetime(2026, 8, 14, 15, 0, tzinfo=UTC)


@dataclass(frozen=True)
class Case:
    """One real flight, one scenario, one hand-derived expectation."""

    flight: str  # the real flight number
    airline: str  # IATA code of the real operating carrier
    origin: str
    destination: str
    departure_delay: float | None
    arrival_delay: float | None
    expected_verdict: Verdict
    why: str  # the hand-derived reasoning
    expected_regulation: str | None = None
    expected_amount: str | None = None
    expected_currency: str | None = None
    status: FlightStatus = FlightStatus.LANDED
    also_eligible_under: tuple[str, ...] = field(default=())

    @property
    def label(self) -> str:
        return f"{self.flight} {self.origin}->{self.destination}"


CASES: tuple[Case, ...] = (
    # --- Israeli law: the 8-hour departure threshold ------------------------
    Case(
        "LY315", "LY", "TLV", "JFK", 3.5, 3.5, Verdict.NOT_ELIGIBLE,
        "El Al out of Tel Aviv. Outside the EU and the UK entirely. Israeli law "
        "covers it but measures DEPARTURE delay, and 3h30 is far below 8h.",
    ),
    Case(
        "LY315", "LY", "TLV", "JFK", 10.0, 10.0, Verdict.ELIGIBLE,
        "Same flight, 10h late off the stand. Israeli law: 10h >= 8h. 9,117 km "
        "is over 4,500 so the top band, ILS3,670. Arrival 10h exceeds the 6h "
        "ceiling for that band, so no reduction.",
        "ISRAEL", "3670.00", "ILS",
    ),
    Case(
        "6H1", "6H", "TLV", "ETM", 9.0, 9.0, Verdict.ELIGIBLE,
        "Israir domestic, Tel Aviv to Eilat. 254 km, so the bottom Israeli band "
        "at ILS1,530. Arrival 9h exceeds the 4h ceiling, so paid in full. "
        "Europe is irrelevant: both ends are Israel.",
        "ISRAEL", "1530.00", "ILS",
    ),
    Case(
        "6H1", "6H", "TLV", "ETM", 9.0, 3.0, Verdict.ELIGIBLE,
        "The same domestic flight, but the crew made up time and landed only 3h "
        "late. Still eligible -- departure delay decides that -- but 3h is inside "
        "the 4h ceiling for this band, so the amount is HALVED to ILS765.",
        "ISRAEL", "765.00", "ILS",
    ),
    Case(
        "TK785", "TK", "IST", "TLV", 5.0, 5.0, Verdict.NOT_ELIGIBLE,
        "Turkish Airlines into Tel Aviv. Turkey is not in the EU or the EEA, so "
        "EC261 does not reach it. Israeli law covers the flight but 5h is below "
        "the 8h departure threshold.",
    ),
    Case(
        "TK785", "TK", "IST", "TLV", 9.0, 9.0, Verdict.ELIGIBLE,
        "Same flight 9h late. Israeli law only: 1,166 km is the bottom band, "
        "ILS1,530, and 9h arrival is past the 4h ceiling so no reduction. The "
        "carrier's nationality is irrelevant under Israeli law.",
        "ISRAEL", "1530.00", "ILS",
    ),

    # --- EC261: departing the EU covers ANY airline --------------------------
    Case(
        "AF139", "AF", "CDG", "TLV", 3.5, 3.5, Verdict.ELIGIBLE,
        "Air France out of Paris. Departs the EU, so EC261 applies. 3h30 clears "
        "the 3h threshold and 3,284 km sits in the 1,500-3,500 band: EUR400.",
        "EC261", "400.00", "EUR",
    ),
    Case(
        "LY324", "LY", "CDG", "TLV", 3.5, 3.5, Verdict.ELIGIBLE,
        "THE SAME ROUTE ON EL AL. Still EUR400. Departing the EU covers every "
        "airline regardless of nationality -- this is the half of the rule people "
        "remember.",
        "EC261", "400.00", "EUR",
    ),
    Case(
        "LX257", "LX", "ZRH", "TLV", 4.0, 4.0, Verdict.ELIGIBLE,
        "Swiss out of Zurich. Switzerland is in neither the EU nor the EEA, but "
        "applies EC261 through its air transport agreement with the EU. 2,809 km "
        "-> EUR400.",
        "EC261", "400.00", "EUR",
    ),
    Case(
        "DY1554", "DY", "OSL", "TLV", 4.0, 4.0, Verdict.ELIGIBLE,
        "Norwegian out of Oslo. Norway is not in the EU but IS in the EEA, so "
        "EC261 applies. 3,587 km is just over 3,500: the top band, EUR600.",
        "EC261", "600.00", "EUR",
    ),
    Case(
        "KL462", "KL", "TLV", "AMS", 3.0, 3.0, Verdict.ELIGIBLE,
        "KLM into Amsterdam, delayed EXACTLY 3 hours. The regulation says three "
        "hours or more, so this qualifies. Arriving into the EU on an EU carrier "
        "is covered. 3,312 km -> EUR400.",
        "EC261", "400.00", "EUR",
    ),

    # --- EC261: arriving into the EU covers only EU carriers -----------------
    Case(
        "LH687", "LH", "TLV", "FRA", 3.5, 3.5, Verdict.ELIGIBLE,
        "Lufthansa into Frankfurt. Arriving into the EU, and Lufthansa is a "
        "Community carrier, so EC261 applies. 2,953 km -> EUR400.",
        "EC261", "400.00", "EUR",
    ),
    Case(
        "LY355", "LY", "TLV", "FRA", 3.5, 3.5, Verdict.NOT_ELIGIBLE,
        "THE SAME ROUTE ON EL AL, and now nothing is owed. The flight only "
        "ARRIVES into the EU, and El Al is not a Community carrier. This is the "
        "half of the rule people forget, and getting it wrong pays out EUR400 "
        "that is not owed.",
    ),

    # --- UK261 --------------------------------------------------------------
    Case(
        "BA165", "BA", "TLV", "LHR", 4.0, 4.0, Verdict.ELIGIBLE,
        "British Airways into Heathrow. UK261 covers arrivals into the UK on a "
        "UK carrier. 3,589 km is over 3,500: GBP520. EC261 does not apply -- "
        "neither end is in the EU.",
        "UK261", "520.00", "GBP",
    ),
    Case(
        "LY317", "LY", "TLV", "LHR", 4.0, 4.0, Verdict.NOT_ELIGIBLE,
        "THE SAME ROUTE ON EL AL. Arriving into the UK on a carrier that is "
        "neither British nor EU-licensed, so UK261 does not reach it either.",
    ),
    Case(
        "LH2472", "LH", "TLV", "LHR", 4.0, 4.0, Verdict.ELIGIBLE,
        "The same route again, this time on Lufthansa. UK261 kept EU-licensed "
        "carriers inside its arrivals rule, so a German airline into Heathrow IS "
        "covered. GBP520.",
        "UK261", "520.00", "GBP",
    ),
    Case(
        "BA112", "BA", "JFK", "LHR", 4.0, 4.0, Verdict.ELIGIBLE,
        "British Airways New York to London. 5,540 km -> GBP520. Nothing to do "
        "with Israel or the EU.",
        "UK261", "520.00", "GBP",
    ),
    Case(
        "AA100", "AA", "JFK", "LHR", 4.0, 4.0, Verdict.NOT_ELIGIBLE,
        "The identical route on American Airlines. Arriving into the UK on a US "
        "carrier, so UK261 does not apply. Same two airports, same delay, "
        "nothing owed.",
    ),
    Case(
        "U28402", "U2", "LGW", "BCN", 3.0833, 3.0833, Verdict.ELIGIBLE,
        "easyJet UK out of Gatwick. Departing the UK covers any airline: GBP220 "
        "for 1,109 km. EC261 does NOT apply -- the flight only arrives into the "
        "EU, and easyJet UK is a British AOC, not an EU one.",
        "UK261", "220.00", "GBP",
    ),

    # --- Two laws at once ----------------------------------------------------
    Case(
        "BA165", "BA", "TLV", "LHR", 9.0, 9.0, Verdict.ELIGIBLE,
        "The headline case. 9h late: UK261 pays GBP520 AND Israeli law pays "
        "ILS2,450 (band 2,000-4,500, arrival past the 5h ceiling). Converted for "
        "ranking only, ILS2,450 is about EUR612 against GBP520's EUR608, so the "
        "Israeli award leads -- by four euro.",
        "ISRAEL", "2450.00", "ILS", also_eligible_under=("UK261",),
    ),
    Case(
        "BA165", "BA", "TLV", "LHR", 9.0, 4.5, Verdict.ELIGIBLE,
        "The same flight, but the crew made up time and landed 4h30 late. UK261 "
        "still pays GBP520 in full -- it measures arrival, and 4h30 clears 3h. "
        "The Israeli award is HALVED to ILS1,225, because 4h30 is inside the 5h "
        "ceiling. Now GBP520 leads.",
        "UK261", "520.00", "GBP", also_eligible_under=("ISRAEL",),
    ),
    Case(
        "FR7012", "FR", "DUB", "STN", 3.25, 3.25, Verdict.ELIGIBLE,
        "Ryanair Dublin to Stansted. Departs the EU (EC261, EUR250) and arrives "
        "into the UK on an EU carrier (UK261, GBP220). Both apply. GBP220 is "
        "about EUR257, so UK261 leads.",
        "UK261", "220.00", "GBP", also_eligible_under=("EC261",),
    ),
    Case(
        "FI450", "FI", "KEF", "LHR", 3.5, 3.5, Verdict.ELIGIBLE,
        "Icelandair Reykjavik to London. Departs the EEA (EC261, EUR400 for "
        "1,895 km) and arrives into the UK on an EEA carrier (UK261, GBP350). "
        "GBP350 is about EUR410, so UK261 leads.",
        "UK261", "350.00", "GBP", also_eligible_under=("EC261",),
    ),

    # --- The two clocks ------------------------------------------------------
    Case(
        "EI154", "EI", "DUB", "LHR", 9.0, 1.0, Verdict.NOT_ELIGIBLE,
        "Aer Lingus pushed back NINE HOURS late and still landed only 1h late. "
        "Nothing is owed anywhere. EC261 and UK261 measure arrival; Israeli law "
        "would have paid on that departure delay, but neither end is Israel. An "
        "implementation reading departure delay would wrongly pay EUR250.",
    ),

    # --- The measurement margin ----------------------------------------------
    Case(
        "W62361", "W6", "TLV", "BUD", 2.8333, 2.8333, Verdict.NEEDS_REVIEW,
        "Wizz Air into Budapest, landing 2h50 late by the database. Too close to "
        "call: flight data records touchdown, but Germanwings put arrival at the "
        "moment a door opens -- five to fifteen minutes later. This passenger may "
        "legally be over three hours, so we ask rather than deny.",
    ),
    Case(
        "W62361", "W6", "TLV", "BUD", 2.5, 2.5, Verdict.NOT_ELIGIBLE,
        "The same flight 2h30 late. Comfortably short even allowing for the "
        "touchdown-versus-doors difference, so this is a confident no.",
    ),

    # --- Cancellation --------------------------------------------------------
    Case(
        "LH687", "LH", "TLV", "FRA", None, None, Verdict.LIKELY_ELIGIBLE,
        "Lufthansa cancelled. Both EC261 and Israeli law cover the flight, and "
        "both turn on how much notice the passenger was given -- which no flight "
        "database records, but the passenger does. So the amount is stated and "
        "the question is asked. 2,953 km puts EC261 in the middle band: EUR400, "
        "against ILS2,450 under the Israeli law, and the shekel figure is worth "
        "more.",
        "ISRAEL", "2450.00", "ILS",
        status=FlightStatus.CANCELLED,
    ),
)


def build(case: Case) -> FlightFacts:
    origin, destination = find_airport(case.origin), find_airport(case.destination)
    airline = find_airline(case.airline)
    assert origin and destination and airline, case.label

    return FlightFacts(
        flight_number=case.flight,
        flight_date=date(2026, 8, 14),
        airline_iata=airline.iata,
        airline_country=airline.country,
        origin_iata=origin.iata,
        origin_country=origin.country,
        destination_iata=destination.iata,
        destination_country=destination.country,
        distance_km=distance_between(origin, destination),
        scheduled_departure=SCHEDULED_DEPARTURE,
        scheduled_arrival=SCHEDULED_ARRIVAL,
        actual_departure=(
            None if case.departure_delay is None
            else SCHEDULED_DEPARTURE + timedelta(hours=case.departure_delay)
        ),
        actual_arrival=(
            None if case.arrival_delay is None
            else SCHEDULED_ARRIVAL + timedelta(hours=case.arrival_delay)
        ),
        status=case.status,
    )


@pytest.mark.parametrize("case", CASES, ids=lambda c: f"{c.label}_{c.arrival_delay}")
def test_real_flight(case: Case) -> None:
    result = engine.evaluate(build(case))

    assert result.verdict is case.expected_verdict, (
        f"\n{case.label}\nExpected {case.expected_verdict.value}, got "
        f"{result.verdict.value}\nReasoning: {case.why}\n"
        + "\n".join(f"  {o.regulation}: {o.reason}" for o in result.outcomes)
    )

    if case.expected_regulation is not None:
        assert result.best_regulation == case.expected_regulation, case.why
        assert result.best_award is not None
        assert str(result.best_award.amount) == case.expected_amount, case.why
        assert result.best_award.currency.value == case.expected_currency, case.why

    if case.also_eligible_under:
        eligible = {o.regulation for o in result.eligible_outcomes}
        for regulation in case.also_eligible_under:
            assert regulation in eligible, (
                f"{case.label}: expected {regulation} to pay as well. {case.why}"
            )


def test_every_case_uses_a_real_airport_and_airline() -> None:
    """Guards the premise of this whole file.

    A typo'd airport code would silently drop the case rather than fail it,
    leaving a test that proves nothing while looking like it passes.
    """
    for case in CASES:
        assert find_airport(case.origin), f"{case.label}: unknown origin"
        assert find_airport(case.destination), f"{case.label}: unknown destination"
        assert find_airline(case.airline), f"{case.label}: unknown airline"


def test_the_suite_covers_every_verdict() -> None:
    """If a refactor made everything one verdict, this file should notice."""
    verdicts = {case.expected_verdict for case in CASES}
    assert verdicts == {
        Verdict.ELIGIBLE,
        Verdict.LIKELY_ELIGIBLE,
        Verdict.NOT_ELIGIBLE,
        Verdict.NEEDS_REVIEW,
    }


def test_the_suite_covers_all_three_regulations() -> None:
    regulations = {c.expected_regulation for c in CASES if c.expected_regulation}
    assert regulations == {"EC261", "UK261", "ISRAEL"}
