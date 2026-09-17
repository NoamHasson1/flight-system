"""Tests for the eligibility use case.

Integration rather than unit: these run the real provider port, the real
mapper and the real rules together. Every layer is already tested alone, so
what is checked here is that they agree with each other -- and above all that
no path through them can turn a failure into a denial.
"""

from datetime import date

import pytest

from app.domain.models import Verdict
from app.providers.registry import build_provider
from app.services.eligibility import CheckStatus, check

AUG_14 = date(2026, 8, 14)
AUG_20 = date(2026, 8, 20)


@pytest.fixture
def provider():  # type: ignore[no-untyped-def]
    return build_provider("fake")


# --- Deciding ----------------------------------------------------------------


async def test_a_delayed_flight_is_decided(provider) -> None:  # type: ignore[no-untyped-def]
    """TLV -> LHR, four hours late. Eligible under UK261 alone."""
    outcome = await check(provider, "BA165", AUG_14)
    assert outcome.status is CheckStatus.DECIDED
    assert outcome.verdict is Verdict.ELIGIBLE
    assert outcome.result is not None
    assert outcome.result.best_regulation == "UK261"
    assert str(outcome.result.best_award) == "£520.00"


async def test_two_laws_can_both_pay(provider) -> None:  # type: ignore[no-untyped-def]
    outcome = await check(provider, "BA165", AUG_20)
    assert outcome.result is not None
    assert len(outcome.result.eligible_outcomes) == 2


async def test_a_flight_outside_every_law_is_a_confident_no(provider) -> None:  # type: ignore[no-untyped-def]
    """TLV -> CDG on El Al: arriving into the EU on a non-EU carrier.

    The system must still be willing to say no, or the product is useless.
    """
    outcome = await check(provider, "LY325", AUG_14)
    assert outcome.verdict is Verdict.NOT_ELIGIBLE
    assert outcome.result is not None
    assert len(outcome.result.outcomes) == 3


async def test_the_flight_facts_come_back_with_the_verdict(provider) -> None:  # type: ignore[no-untyped-def]
    """The caller needs the flight to display and to store, and should not have
    to re-derive it."""
    outcome = await check(provider, "BA165", AUG_14)
    assert outcome.flight is not None
    assert outcome.flight.route == "TLV → LHR"
    assert outcome.flight.distance_km == pytest.approx(3588.6, abs=1.0)


async def test_the_raw_provider_record_is_carried_through(provider) -> None:  # type: ignore[no-untyped-def]
    """So the check can be stored with exactly what the provider said, and
    re-run later against corrected rules without paying for the lookup again."""
    outcome = await check(provider, "BA165", AUG_14)
    assert outcome.raw is not None
    assert outcome.raw.provider == "fake"


# --- Not found ---------------------------------------------------------------


async def test_an_unknown_flight_is_not_found_not_ineligible(provider) -> None:  # type: ignore[no-untyped-def]
    """A typo is not a legal conclusion.

    NOT_FOUND carries no verdict at all -- it is a question, not an answer --
    and the message says the date means the day of departure, which is the
    commonest reason a real flight cannot be found.
    """
    outcome = await check(provider, "XX999", AUG_14)
    assert outcome.status is CheckStatus.NOT_FOUND
    assert outcome.verdict is None
    assert "check the flight number" in outcome.message  # type: ignore[operator]
    assert "day the flight departed" in outcome.message  # type: ignore[operator]


# --- Several matches ---------------------------------------------------------


async def test_several_matches_ask_which_one(provider) -> None:  # type: ignore[no-untyped-def]
    """FR1234 flew Dublin to Stansted twice that day: 11 minutes late and
    4h 35m late.

    Guessing would tell half of those passengers a confident answer about a
    journey they did not take. So there is no verdict here -- only a question.
    """
    outcome = await check(provider, "FR1234", AUG_14)
    assert outcome.status is CheckStatus.AMBIGUOUS
    assert outcome.verdict is None
    assert len(outcome.options) == 2
    assert all("DUB → STN" in o.label for o in outcome.options)


async def test_choosing_an_option_resolves_it(provider) -> None:  # type: ignore[no-untyped-def]
    """The customer picks their flight and asks again.

    The late one is eligible; the punctual one is not. Same number, same date.
    """
    ambiguous = await check(provider, "FR1234", AUG_14)
    verdicts = {}
    for option in ambiguous.options:
        resolved = await check(provider, "FR1234", AUG_14, option_key=option.key)
        assert resolved.status is CheckStatus.DECIDED
        verdicts[option.key] = resolved.verdict
    assert set(verdicts.values()) == {Verdict.ELIGIBLE, Verdict.NOT_ELIGIBLE}


async def test_option_keys_are_stable_rather_than_positional(provider) -> None:  # type: ignore[no-untyped-def]
    """A list index would silently select a different flight if the provider
    returned the matches in another order next time."""
    first = await check(provider, "FR1234", AUG_14)
    second = await check(provider, "FR1234", AUG_14)
    assert [o.key for o in first.options] == [o.key for o in second.options]
    assert "DUB-STN-" in first.options[0].key


async def test_an_option_key_that_no_longer_matches_is_not_found(provider) -> None:  # type: ignore[no-untyped-def]
    outcome = await check(provider, "FR1234", AUG_14, option_key="NOPE")
    assert outcome.status is CheckStatus.NOT_FOUND


# --- Everything that must not become a denial --------------------------------
#
# The point of this whole module. Each case below is a way the lookup can fail,
# and not one of them may reach the customer as "you have no claim".


@pytest.mark.parametrize(
    ("number", "expected_phrase"),
    [
        ("ERR503", "did not respond"),
        ("ERR429", "limit for flight lookups"),
        ("ERR401", "problem on our side"),
        ("ERR422", "did not respond"),
    ],
)
async def test_provider_failures_become_needs_review(  # type: ignore[no-untyped-def]
    provider, number: str, expected_phrase: str
) -> None:
    """An outage is not evidence about anybody's flight.

    The four failures are distinguished only where the distinction changes what
    the customer should do next. The exception text never reaches them: it names
    vendors and status codes and helps nobody.
    """
    outcome = await check(provider, number, AUG_14)
    assert outcome.status is CheckStatus.UNRESOLVED
    assert outcome.verdict is Verdict.NEEDS_REVIEW
    assert expected_phrase in outcome.message  # type: ignore[operator]
    assert number not in outcome.message  # type: ignore[operator]


async def test_the_outage_message_tells_them_not_to_assume(provider) -> None:  # type: ignore[no-untyped-def]
    """The most important sentence the system writes.

    Someone who reads "we could not check" and closes the tab has lost a claim
    they may well have had, and nobody will ever know.
    """
    outcome = await check(provider, "ERR503", AUG_14)
    assert "do not assume you have no claim" in outcome.message  # type: ignore[operator]


async def test_an_unmappable_flight_becomes_needs_review(provider) -> None:  # type: ignore[no-untyped-def]
    """A gap in OUR reference data, reported as our gap.

    ZZZ is not an airport we carry. Without a country we cannot say which law
    applies; without coordinates we cannot say how much.
    """
    outcome = await check(provider, "ZZ999", AUG_14)
    assert outcome.status is CheckStatus.UNRESOLVED
    assert outcome.verdict is Verdict.NEEDS_REVIEW
    assert "We could not fully identify" in outcome.message  # type: ignore[operator]
    assert "ZZZ" in outcome.message  # type: ignore[operator]


async def test_needs_human_attention_flags_every_review(provider) -> None:  # type: ignore[no-untyped-def]
    """One property the admin queue can filter on, whatever caused the review."""
    for number in ("ERR503", "ZZ999", "LH687"):
        assert (await check(provider, number, AUG_14)).needs_human_attention

    for number in ("BA165", "LY325"):
        assert not (await check(provider, number, AUG_14)).needs_human_attention


# --- Normalisation -----------------------------------------------------------


@pytest.mark.parametrize("number", ["ba165", " BA165 ", "Ba165"])
async def test_flight_numbers_are_normalised(provider, number: str) -> None:  # type: ignore[no-untyped-def]
    outcome = await check(provider, number, AUG_14)
    assert outcome.flight_number == "BA165"
    assert outcome.verdict is Verdict.ELIGIBLE


async def test_the_result_records_which_provider_answered(provider) -> None:  # type: ignore[no-untyped-def]
    """Stored with the check, so a verdict can always be traced to its source --
    which matters most when the source turns out to have been wrong."""
    assert (await check(provider, "BA165", AUG_14)).provider == "fake"
