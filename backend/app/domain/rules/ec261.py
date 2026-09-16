"""EC261 -- Regulation (EC) No 261/2004.

The structure mirrors section 5 of rules.md exactly, in the same order:

    1. Does this law apply at all?   -> applies()
    2. Was the disruption bad enough? -> the delay threshold
    3. How much money is owed?        -> compensation_for()

Every figure below is a named constant. When these change, exactly one file
changes, and rules.md is updated to match.
"""

from __future__ import annotations

from app.domain.models import Currency, FlightFacts, FlightStatus, Money, Verdict
from app.domain.rules.base import (
    EC261_CARRIER_STATES,
    EC261_TERRITORIES,
    RegulationOutcome,
    distance_band,
    format_hours,
)

CODE = "EC261"
NAME = "Regulation (EC) No 261/2004"

# --- The numbers -------------------------------------------------------------

BAND_1_KM = 1500.0
BAND_2_KM = 3500.0
MINIMUM_ARRIVAL_DELAY_HOURS = 3.0

COMPENSATION: tuple[Money, Money, Money] = (
    Money.of("250", Currency.EUR),  # 1,500 km or less
    Money.of("400", Currency.EUR),  # 1,500 - 3,500 km
    Money.of("600", Currency.EUR),  # over 3,500 km
)

# Article 7(2)(c): on the longest flights the airline may pay half if it still
# gets the passenger there within four hours. The passenger is still eligible at
# three -- they simply receive 50%. This only ever bites in the narrow window
# between 3 and 4 hours on flights over 3,500 km.
LONG_HAUL_REDUCTION_BELOW_HOURS = 4.0


# --- 1. Does this law apply at all? ------------------------------------------


def applies(flight: FlightFacts) -> bool:
    """True if EC261 covers this flight.

    The rule is deliberately asymmetric, and the asymmetry is what people get
    wrong:

      * DEPARTING the EU/EEA covers *every* airline, wherever it is from.
      * ARRIVING into the EU/EEA only covers EU-licensed carriers.

    So El Al flying Paris -> Tel Aviv is covered, because it departs France.
    El Al flying Tel Aviv -> Frankfurt is not, because El Al is not a Community
    carrier and the flight only arrives.
    """
    departs_from_eu = flight.origin_country in EC261_TERRITORIES
    arrives_in_eu = flight.destination_country in EC261_TERRITORIES
    is_community_carrier = flight.airline_country in EC261_CARRIER_STATES

    return departs_from_eu or (arrives_in_eu and is_community_carrier)


# --- 3. How much money is owed? ----------------------------------------------


def compensation_for(distance_km: float, arrival_delay_hours: float) -> Money:
    """The award for a flight of this distance and this delay."""
    band = distance_band(distance_km, BAND_1_KM, BAND_2_KM)
    award = COMPENSATION[band]

    is_long_haul = band == 2
    arrived_within_four_hours = arrival_delay_hours < LONG_HAUL_REDUCTION_BELOW_HOURS
    if is_long_haul and arrived_within_four_hours:
        return award.halved()
    return award


# --- Putting it together -----------------------------------------------------


def evaluate(flight: FlightFacts) -> RegulationOutcome:
    """Apply EC261 to one flight."""
    if not applies(flight):
        return _outcome(
            Verdict.NOT_ELIGIBLE,
            applies=False,
            reason=(
                f"EC261 does not cover this flight: it departs from "
                f"{flight.origin_country} and arrives in {flight.destination_country}, "
                f"and the operating carrier {flight.airline_iata} is licensed in "
                f"{flight.airline_country}. The regulation covers flights leaving the "
                f"EU/EEA on any airline, or arriving into the EU/EEA on an EU carrier."
            ),
        )

    # From here the law applies, so every remaining answer is about this flight's
    # facts -- and anything we cannot establish becomes NEEDS_REVIEW rather than
    # a confident "no".

    if flight.status is FlightStatus.DIVERTED:
        return _review("the flight was diverted, which needs a person to assess")

    if flight.status is FlightStatus.UNKNOWN:
        return _review("we could not establish what happened to this flight")

    if flight.is_cancelled:
        # Cancellation compensation turns on how much notice the passenger was
        # given -- under 14 days and it is payable. No flight data API reports
        # that, and it is not ours to assume in either direction.
        return _review(
            "the flight was cancelled. Compensation is payable when the airline "
            "gave less than 14 days' notice, which we need to confirm with you"
        )

    delay = flight.arrival_delay_hours
    if delay is None:
        return _review(
            "the flight has no recorded arrival time yet, so the delay cannot "
            "be measured"
        )

    if delay < MINIMUM_ARRIVAL_DELAY_HOURS:
        return _outcome(
            Verdict.NOT_ELIGIBLE,
            applies=True,
            reason=(
                f"EC261 covers this flight, but it arrived {format_hours(delay)} late, "
                f"below the {format_hours(MINIMUM_ARRIVAL_DELAY_HOURS)} threshold."
            ),
        )

    award = compensation_for(flight.distance_km, delay)
    band_note = _describe_band(flight.distance_km, delay, award)
    return _outcome(
        Verdict.ELIGIBLE,
        applies=True,
        award=award,
        reason=(
            f"EC261 covers this flight ({flight.route}). It arrived "
            f"{format_hours(delay)} late, at or over the "
            f"{format_hours(MINIMUM_ARRIVAL_DELAY_HOURS)} threshold. {band_note}"
        ),
    )


def _describe_band(distance_km: float, delay: float, award: Money) -> str:
    band = distance_band(distance_km, BAND_1_KM, BAND_2_KM)
    full = COMPENSATION[band]
    descriptions = (
        f"The distance of {distance_km:,.0f} km is {BAND_1_KM:,.0f} km or less",
        f"The distance of {distance_km:,.0f} km is between {BAND_1_KM:,.0f} and "
        f"{BAND_2_KM:,.0f} km",
        f"The distance of {distance_km:,.0f} km is over {BAND_2_KM:,.0f} km",
    )
    if award != full:
        return (
            f"{descriptions[band]}, giving {full}, halved to {award} because the "
            f"airline landed you within "
            f"{format_hours(LONG_HAUL_REDUCTION_BELOW_HOURS)}."
        )
    return f"{descriptions[band]}, giving {award}."


def _outcome(
    verdict: Verdict, *, applies: bool, reason: str, award: Money | None = None
) -> RegulationOutcome:
    return RegulationOutcome(
        regulation=CODE, verdict=verdict, reason=reason, applies=applies, award=award
    )


def _review(detail: str) -> RegulationOutcome:
    return _outcome(
        Verdict.NEEDS_REVIEW,
        applies=True,
        reason=f"EC261 covers this flight, but {detail}.",
    )
