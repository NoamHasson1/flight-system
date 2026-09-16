"""Runs all three regulations and answers the question the customer asked.

Every law is evaluated, every time. We never stop at the first hit: a single
flight can qualify under two regulations, and a passenger who is shown only one
of them has been short-changed by our software rather than by their airline.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.domain.models import FlightFacts, Money, Verdict
from app.domain.rules import ec261, israel, uk261
from app.domain.rules.base import RegulationEvaluator, RegulationOutcome

# Order matters only for presentation and for breaking ties deterministically.
EVALUATORS: tuple[RegulationEvaluator, ...] = (
    ec261.evaluate,
    uk261.evaluate,
    israel.evaluate,
)

# Shown whenever there is a claim to make or a question to answer. No flight
# data API reports *why* a flight was late, and weather or an air traffic
# control strike excuses the airline entirely -- so this is the one thing the
# system genuinely cannot decide, and it says so rather than pretending.
EXTRAORDINARY_CIRCUMSTANCES_CAVEAT = (
    "This assumes the disruption was within the airline's control. Airlines do "
    "not have to pay when the cause was extraordinary -- severe weather, an air "
    "traffic control strike, a security threat. No flight database records the "
    "reason, so we will ask you what the airline told you."
)

# --- Comparing amounts across currencies -------------------------------------
#
# Ranking 600 euro against 520 pounds against 3,670 shekels needs an exchange
# rate. These are deliberately approximate and deliberately hardcoded, because
# they are used for ONE thing: deciding which award to show first.
#
# They are NEVER used to convert a payout. Compensation amounts are fixed by
# statute in their own currency; a passenger owed 520 pounds is owed 520 pounds,
# not "about 600 euro". Every amount is displayed as the law sets it.
#
# Being out of date therefore cannot produce a wrong payout. The worst it can do
# is order two near-identical options the other way round.
_APPROXIMATE_EUR_RATES: dict[str, Decimal] = {
    "EUR": Decimal("1.00"),
    "GBP": Decimal("1.17"),
    "ILS": Decimal("0.25"),
}


def _ranking_value(award: Money) -> Decimal:
    """Roughly what this award is worth in euro. For sorting only."""
    return award.amount * _APPROXIMATE_EUR_RATES[award.currency.value]


# --- The result --------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EligibilityResult:
    """The complete answer: one verdict, and the reasoning behind all three."""

    verdict: Verdict
    outcomes: tuple[RegulationOutcome, ...]
    best_award: Money | None = None
    best_regulation: str | None = None
    caveat: str | None = None

    @property
    def eligible_outcomes(self) -> tuple[RegulationOutcome, ...]:
        """Every law that pays, best first. Usually one; sometimes two."""
        return tuple(o for o in self.outcomes if o.verdict is Verdict.ELIGIBLE)

    @property
    def review_outcomes(self) -> tuple[RegulationOutcome, ...]:
        """Every law with an open question. These are what to ask the customer."""
        return tuple(o for o in self.outcomes if o.verdict is Verdict.NEEDS_REVIEW)

    @property
    def applicable_outcomes(self) -> tuple[RegulationOutcome, ...]:
        """Every law that covered the flight at all, whatever it concluded."""
        return tuple(o for o in self.outcomes if o.applies)


# --- The engine --------------------------------------------------------------


def evaluate(flight: FlightFacts) -> EligibilityResult:
    """Run every regulation against one flight and combine the answers."""
    outcomes = tuple(evaluate_one(flight) for evaluate_one in EVALUATORS)

    paying = sorted(
        (o for o in outcomes if o.verdict is Verdict.ELIGIBLE),
        key=_by_value_then_declaration_order(outcomes),
    )

    if paying:
        # At least one law pays, so the answer is yes -- even if another law
        # still has an open question. A definite claim outranks an uncertain
        # one, and the uncertain one is still listed in `outcomes`.
        best = paying[0]
        assert best.award is not None  # guaranteed by RegulationOutcome
        return EligibilityResult(
            verdict=Verdict.ELIGIBLE,
            outcomes=_ordered(outcomes, paying),
            best_award=best.award,
            best_regulation=best.regulation,
            caveat=EXTRAORDINARY_CIRCUMSTANCES_CAVEAT,
        )

    if any(o.verdict is Verdict.NEEDS_REVIEW for o in outcomes):
        # Nothing pays outright, but something is unresolved. This must not
        # become a "no": an unanswered question is not the same as a denial,
        # and a wrong denial is the error nobody ever discovers.
        return EligibilityResult(
            verdict=Verdict.NEEDS_REVIEW,
            outcomes=outcomes,
            caveat=EXTRAORDINARY_CIRCUMSTANCES_CAVEAT,
        )

    # Every law was asked, every law answered, and every answer was no. This is
    # a complete, confident result -- and `outcomes` explains it law by law.
    return EligibilityResult(verdict=Verdict.NOT_ELIGIBLE, outcomes=outcomes)


def _by_value_then_declaration_order(
    outcomes: tuple[RegulationOutcome, ...],
) -> object:
    """Sort key: highest award first, ties broken by EVALUATORS order.

    The tie-break exists so the same flight always produces the same answer.
    Two laws can pay amounts that convert to near-identical figures -- 520
    pounds and 600 euro are within a few percent -- and a result that flipped
    between runs would be impossible to support or to test.
    """
    order = {o.regulation: i for i, o in enumerate(outcomes)}

    def key(outcome: RegulationOutcome) -> tuple[Decimal, int]:
        assert outcome.award is not None
        return (-_ranking_value(outcome.award), order[outcome.regulation])

    return key


def _ordered(
    outcomes: tuple[RegulationOutcome, ...], paying: list[RegulationOutcome]
) -> tuple[RegulationOutcome, ...]:
    """Paying laws first, best first; everything else in declaration order.

    The customer should read the money before the explanations of why other
    laws did not apply.
    """
    rest = [o for o in outcomes if o not in paying]
    return tuple(paying) + tuple(rest)
