"""Tests for the decision engine.

The three individual laws are already tested to death. This file tests only the
combining: how three answers become one, how awards in three currencies are
ranked, and what must never be lost along the way.
"""

import pytest

from app.domain.models import Currency, FlightStatus, Money, Verdict
from app.domain.rules import engine
from app.domain.rules.engine import EligibilityResult
from tests.unit.builders import a_flight


def tlv_lhr(**overrides: object) -> object:
    """TLV -> LHR on British Airways: covered by UK261 and by Israeli law, and
    not by EC261. The most useful shape in this file, because it is the one
    route where two regulations genuinely compete."""
    base: dict[str, object] = {
        "flight_number": "BA165", "airline": "BA", "airline_country": "GB",
        "origin": "TLV", "origin_country": "IL",
        "destination": "LHR", "destination_country": "GB",
        "distance_km": 3588.6,
    }
    base.update(overrides)
    return a_flight(**base)  # type: ignore[arg-type]


# --- Every law is always consulted -------------------------------------------


def test_all_three_regulations_are_always_evaluated() -> None:
    """No short-circuiting, ever.

    Stopping at the first law that pays would hide a second, larger claim. The
    outcome list is also what the customer reads, so a missing entry reads as
    though we never checked.
    """
    result = engine.evaluate(tlv_lhr(arrival_delay_hours=4.0))
    assert {o.regulation for o in result.outcomes} == {"EC261", "UK261", "ISRAEL"}


def test_outcomes_are_returned_even_when_nothing_pays() -> None:
    """A "no" has to be explainable law by law, or it is just a shrug."""
    result = engine.evaluate(tlv_lhr(arrival_delay_hours=1.0,
                                     departure_delay_hours=1.0))
    assert result.verdict is Verdict.NOT_ELIGIBLE
    assert len(result.outcomes) == 3
    assert all(o.reason for o in result.outcomes)


# --- Precedence: turning three verdicts into one -----------------------------


def test_one_eligible_law_makes_the_whole_answer_eligible() -> None:
    """UK261 pays, EC261 does not, Israel does not. The customer is eligible."""
    result = engine.evaluate(tlv_lhr(arrival_delay_hours=4.0,
                                     departure_delay_hours=4.0))
    assert result.verdict is Verdict.ELIGIBLE
    assert result.best_regulation == "UK261"
    assert result.best_award == Money.of("520", Currency.GBP)


def test_eligible_beats_needs_review() -> None:
    """A definite claim outranks an open question.

    Departed 9h late and landed 9h late, but the flight was en route with no
    arrival time -- no. Here: UK261 pays outright while Israel still has a
    question. The answer is yes, and the Israeli question stays visible in
    `outcomes` rather than downgrading the whole result.
    """
    flight = tlv_lhr(departure_delay_hours=9.0, arrival_delay_hours=4.0)
    result = engine.evaluate(flight)
    assert result.verdict is Verdict.ELIGIBLE
    assert result.best_regulation in {"UK261", "ISRAEL"}


def test_a_cancelled_flight_is_priced_rather_than_shelved() -> None:
    """Nothing pays outright, but the amount is known and the gap is one fact.

    A cancelled Tel Aviv to Heathrow flight: UK261 and the Israeli law both
    cover it, both can price it, and both wait on the same question -- when did
    the airline tell you.

    This must not collapse to "no": an unanswered question is not a denial, and
    a wrong denial is the error nobody ever discovers. It must also not
    collapse to a blank "we will look into it", which is what the passenger
    reads as a no anyway.
    """
    result = engine.evaluate(
        tlv_lhr(status=FlightStatus.CANCELLED, arrival_delay_hours=None,
                departure_delay_hours=None)
    )
    assert result.verdict is Verdict.LIKELY_ELIGIBLE
    assert result.best_award is not None
    assert result.open_questions == ("cancellation_notice",)


def test_a_definite_payout_outranks_a_provisional_one() -> None:
    """A flight that actually landed late and is owed money is not "likely".

    Ordering matters because the headline verdict is what the customer reads.
    """
    result = engine.evaluate(tlv_lhr(arrival_delay_hours=4.0))
    assert result.verdict is Verdict.ELIGIBLE


def test_a_provisional_payout_outranks_needing_review() -> None:
    """Between "here is the amount, one question" and "we cannot tell", the
    first is strictly more useful and strictly as honest."""
    cancelled = engine.evaluate(
        tlv_lhr(status=FlightStatus.CANCELLED, arrival_delay_hours=None,
                departure_delay_hours=None)
    )
    unknown = engine.evaluate(
        tlv_lhr(status=FlightStatus.UNKNOWN, arrival_delay_hours=None,
                departure_delay_hours=None)
    )
    assert cancelled.verdict is Verdict.LIKELY_ELIGIBLE
    assert unknown.verdict is Verdict.NEEDS_REVIEW


def test_all_three_saying_no_is_a_confident_no() -> None:
    """Every law asked, every law answered, every answer no.

    This is the one case where NOT_ELIGIBLE is the honest result, and the
    engine must be willing to say it -- otherwise every check ends in review
    and the product is useless.
    """
    result = engine.evaluate(
        a_flight(origin_country="US", destination_country="CA",
                 airline_country="US", arrival_delay_hours=1.0,
                 departure_delay_hours=1.0)
    )
    assert result.verdict is Verdict.NOT_ELIGIBLE
    assert result.best_award is None


# --- Two laws paying at once -------------------------------------------------


def test_a_flight_can_pay_under_two_laws_and_both_are_shown() -> None:
    """rules.md example B: TLV -> LHR, 9 hours late.

    UK261 pays 520 pounds and the Israeli law pays 2,450 shekels. Showing only
    one would quietly halve what the passenger knows they can claim.
    """
    result = engine.evaluate(tlv_lhr(arrival_delay_hours=9.0,
                                     departure_delay_hours=9.0))
    assert result.verdict is Verdict.ELIGIBLE
    assert {o.regulation for o in result.eligible_outcomes} == {"UK261", "ISRAEL"}


def test_paying_laws_are_listed_before_the_rest() -> None:
    """The customer should read the money before the explanations."""
    result = engine.evaluate(tlv_lhr(arrival_delay_hours=9.0,
                                     departure_delay_hours=9.0))
    regulations = [o.regulation for o in result.outcomes]
    assert regulations[:2] == [o.regulation for o in result.eligible_outcomes]
    assert regulations[2] == "EC261"  # the one that did not apply


# --- Ranking across currencies -----------------------------------------------


def test_the_larger_award_is_chosen_across_currencies() -> None:
    """2,450 shekels is worth more than 520 pounds, so it leads.

    They are genuinely close -- roughly 612 euro against 608 -- which is
    exactly why a rate table is needed at all rather than a guess.
    """
    result = engine.evaluate(tlv_lhr(arrival_delay_hours=9.0,
                                     departure_delay_hours=9.0))
    assert result.best_regulation == "ISRAEL"
    assert result.best_award == Money.of("2450", Currency.ILS)


def test_eligible_outcomes_are_ordered_best_first() -> None:
    result = engine.evaluate(tlv_lhr(arrival_delay_hours=9.0,
                                     departure_delay_hours=9.0))
    awards = [o.award for o in result.eligible_outcomes]
    assert awards == [Money.of("2450", Currency.ILS), Money.of("520", Currency.GBP)]


def test_the_award_is_never_converted() -> None:
    """The most important test about the rate table.

    Exchange rates are used to ORDER the options and for nothing else. A
    passenger owed 2,450 shekels is owed 2,450 shekels -- not "about 612 euro".
    A stale rate must therefore be incapable of producing a wrong payout; the
    worst it can do is order two near-identical options the other way round.
    """
    result = engine.evaluate(tlv_lhr(arrival_delay_hours=9.0,
                                     departure_delay_hours=9.0))
    assert result.best_award is not None
    assert result.best_award.currency is Currency.ILS
    assert result.best_award.amount == Money.of("2450", Currency.ILS).amount
    for outcome in result.outcomes:
        if outcome.award is not None:
            assert outcome.award in {
                Money.of("2450", Currency.ILS),
                Money.of("520", Currency.GBP),
            }


def test_ranking_is_deterministic() -> None:
    """The same flight must always produce the same answer.

    Two laws can pay amounts that convert to near-identical figures, and a
    result that flipped between runs would be impossible to support or to test.
    """
    flight = tlv_lhr(arrival_delay_hours=9.0, departure_delay_hours=9.0)
    results = [engine.evaluate(flight) for _ in range(20)]
    assert len({r.best_regulation for r in results}) == 1
    assert len({tuple(o.regulation for o in r.outcomes) for r in results}) == 1


# --- The caveat --------------------------------------------------------------


@pytest.mark.parametrize(
    ("delays", "status"),
    [((9.0, 9.0), FlightStatus.LANDED), ((None, None), FlightStatus.CANCELLED)],
)
def test_the_caveat_is_attached_whenever_there_is_something_to_claim(
    delays: tuple[float | None, float | None], status: FlightStatus
) -> None:
    """Both ELIGIBLE and NEEDS_REVIEW carry it.

    The system genuinely cannot tell whether the delay was the airline's fault,
    and telling someone they are definitely owed 600 euro when a thunderstorm
    closed the airport would be worse than useless.
    """
    departure, arrival = delays
    result = engine.evaluate(
        tlv_lhr(departure_delay_hours=departure, arrival_delay_hours=arrival,
                status=status)
    )
    assert result.caveat is not None
    assert "extraordinary" in result.caveat


def test_no_caveat_on_a_confident_no() -> None:
    """Nothing is being claimed, so there is nothing to qualify.

    Adding a caveat to a "no" would only muddy a clear answer.
    """
    result = engine.evaluate(
        a_flight(origin_country="US", destination_country="CA",
                 airline_country="US", arrival_delay_hours=1.0,
                 departure_delay_hours=1.0)
    )
    assert result.caveat is None


# --- The convenience views ---------------------------------------------------


def test_applicable_outcomes_covers_laws_that_reached_the_flight() -> None:
    """Used by the UI to say "two laws covered your flight" without implying
    both paid."""
    result = engine.evaluate(tlv_lhr(arrival_delay_hours=4.0,
                                     departure_delay_hours=4.0))
    assert {o.regulation for o in result.applicable_outcomes} == {"UK261", "ISRAEL"}


def test_two_laws_waiting_on_one_fact_ask_once() -> None:
    """UK261 and the Israeli law both hang on the notice period here.

    Asking the same question twice reads as a system that is not paying
    attention, so the questions are de-duplicated while both outcomes are kept.
    """
    result = engine.evaluate(
        tlv_lhr(status=FlightStatus.CANCELLED, arrival_delay_hours=None,
                departure_delay_hours=None)
    )
    assert len(result.likely_outcomes) == 2
    assert all("14 days" in o.reason for o in result.likely_outcomes)
    assert result.open_questions == ("cancellation_notice",)


def test_the_result_is_immutable() -> None:
    """A verdict is a record of a decision, not a working variable."""
    result = engine.evaluate(tlv_lhr(arrival_delay_hours=4.0))
    with pytest.raises(AttributeError):
        result.verdict = Verdict.NOT_ELIGIBLE  # type: ignore[misc]


# --- The four worked examples from rules.md, end to end ----------------------


def test_rules_md_example_a() -> None:
    """TLV -> LHR, 4 hours late -> eligible, 520 pounds under UK261."""
    result = engine.evaluate(tlv_lhr(arrival_delay_hours=4.0,
                                     departure_delay_hours=4.0))
    assert result.verdict is Verdict.ELIGIBLE
    assert result.best_regulation == "UK261"
    assert result.best_award == Money.of("520", Currency.GBP)


def test_rules_md_example_b() -> None:
    """TLV -> LHR, 9 hours late -> two laws pay; the Israeli one leads."""
    result = engine.evaluate(tlv_lhr(arrival_delay_hours=9.0,
                                     departure_delay_hours=9.0))
    assert result.verdict is Verdict.ELIGIBLE
    assert len(result.eligible_outcomes) == 2
    assert result.best_award == Money.of("2450", Currency.ILS)


def test_rules_md_example_c() -> None:
    """CDG -> TLV on El Al, 3h30 late -> 400 euro under EC261 alone."""
    result = engine.evaluate(
        a_flight(flight_number="LY324", airline="LY", airline_country="IL",
                 origin="CDG", origin_country="FR",
                 destination="TLV", destination_country="IL",
                 distance_km=3283.8, arrival_delay_hours=3.5,
                 departure_delay_hours=3.5)
    )
    assert result.verdict is Verdict.ELIGIBLE
    assert result.best_regulation == "EC261"
    assert result.best_award == Money.of("400", Currency.EUR)


def test_rules_md_example_d() -> None:
    """TLV -> JFK, 2 hours late -> not eligible, and the reason names the
    Israeli law's threshold so the passenger understands why."""
    result = engine.evaluate(
        a_flight(airline="LY", airline_country="IL",
                 origin="TLV", origin_country="IL",
                 destination="JFK", destination_country="US",
                 distance_km=9117.1, arrival_delay_hours=2.0,
                 departure_delay_hours=2.0)
    )
    assert result.verdict is Verdict.NOT_ELIGIBLE
    israeli = next(o for o in result.outcomes if o.regulation == "ISRAEL")
    assert israeli.applies is True
    assert "8h 00m threshold" in israeli.reason


def test_the_result_type_is_constructible_empty() -> None:
    """Guards the dataclass defaults, which a NOT_ELIGIBLE result relies on."""
    result = EligibilityResult(verdict=Verdict.NOT_ELIGIBLE, outcomes=())
    assert result.best_award is None and result.caveat is None
