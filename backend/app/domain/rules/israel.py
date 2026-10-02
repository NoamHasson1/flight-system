"""The Israeli Aviation Services Law -- the "Tibi Law".

Aviation Services Law (Compensation and Assistance for Flight Cancellation or
Change of Conditions), 5772-2012.

Unlike UK261, this is NOT EC261 with different numbers, and it deliberately does
not reuse `base.ArrivalDelayRegulation`. Four things genuinely differ:

  1. It measures the delay at DEPARTURE, not at arrival.
  2. Its threshold is 8 hours, not 3.
  3. Its distance bands are 2,000 / 4,500 km, not 1,500 / 3,500 km.
  4. Its 50% reduction is real. EC261's lives in Article 7(2) and is about being
     re-routed after a cancellation, so it does not reach delay claims. The
     Israeli reduction is written into the delay provision itself, and turns on
     the ARRIVAL delay -- so this law reads both numbers.

Forcing all that into the shared shape would hide a real difference rather than
share a real similarity.

Mirrors section 6 of rules.md.
"""

from __future__ import annotations

from app.domain.models import Currency, FlightFacts, FlightStatus, Money, Verdict
from app.domain.rules.base import (
    OpenQuestion,
    RegulationOutcome,
    describe_delay,
    distance_band,
    format_hours,
)

CODE = "ISRAEL"
NAME = (
    "Aviation Services Law (Compensation and Assistance for Flight Cancellation "
    "or Change of Conditions), 5772-2012"
)
LABEL = "The Israeli Aviation Services Law"

# --- The numbers -------------------------------------------------------------

TERRITORY = frozenset({"IL"})

BAND_1_KM = 2000.0  # note: NOT 1,500 -- the European figure
BAND_2_KM = 4500.0  # note: NOT 3,500

MINIMUM_DEPARTURE_DELAY_HOURS = 8.0

# The most time an aircraft could conceivably make up in the air.
#
# Used only to rule a claim OUT when the departure time is unknown: a
# departure delay is the arrival delay plus whatever was recovered en route,
# so an arrival delay this far below the threshold cannot hide a qualifying
# departure delay.
#
# Deliberately absurd. Real recovery is minutes -- schedules are padded, and
# an aircraft that is already late is not given a better routing. Three hours
# is far beyond anything any flight achieves, which is the point: the number
# has to be wrong by a wide margin before it can produce a wrong "no".
MAX_TIME_MADE_UP_HOURS = 3.0

COMPENSATION: tuple[Money, Money, Money] = (
    Money.of("1530", Currency.ILS),  # 2,000 km or less
    Money.of("2450", Currency.ILS),  # 2,000 - 4,500 km
    Money.of("3670", Currency.ILS),  # over 4,500 km
)

# These shekel amounts are linked to the Israeli consumer price index and are
# re-indexed every year. They live here, in one place, so the annual update is a
# three-line edit with no logic to re-reason about.

# The compensation is halved when the airline still lands the passenger within
# this many hours of schedule. The ceiling widens with distance, and the
# comparison is inclusive: the law says the arrival delay must "not exceed" the
# figure, so a delay of exactly 4h 00m on a short flight is still halved.
REDUCTION_ARRIVAL_CEILING_HOURS: tuple[float, float, float] = (4.0, 5.0, 6.0)


# --- 1. Does this law apply at all? ------------------------------------------


def applies(flight: FlightFacts) -> bool:
    """True if the flight departs from or arrives in Israel.

    Simpler than EC261 and UK261: there is no carrier-nationality test at all.
    Any airline, in either direction.
    """
    return (
        flight.origin_country in TERRITORY or flight.destination_country in TERRITORY
    )


# --- 3. How much money is owed? ----------------------------------------------


def compensation_for(distance_km: float, arrival_delay_hours: float) -> Money:
    """The award, after any reduction.

    Takes the ARRIVAL delay even though eligibility is decided on the DEPARTURE
    delay. That is not a mistake: the law sets the threshold at departure and
    the reduction at arrival, so both numbers are needed.
    """
    band = distance_band(distance_km, BAND_1_KM, BAND_2_KM)
    award = COMPENSATION[band]

    if arrival_delay_hours <= REDUCTION_ARRIVAL_CEILING_HOURS[band]:
        return award.halved()
    return award


# --- Putting it together -----------------------------------------------------


def evaluate(flight: FlightFacts) -> RegulationOutcome:
    """Apply the Israeli Aviation Services Law to one flight."""
    if not applies(flight):
        return _outcome(
            Verdict.NOT_ELIGIBLE,
            applies=False,
            reason=(
                f"{LABEL} does not cover this flight: it departs from "
                f"{flight.origin_country} and arrives in {flight.destination_country}, "
                f"and the law covers flights departing from or arriving in Israel."
            ),
        )

    if flight.status is FlightStatus.DIVERTED:
        return _review("the flight was diverted, which needs a person to assess")

    if flight.status is FlightStatus.UNKNOWN:
        return _review("we could not establish what happened to this flight")

    if flight.is_cancelled:
        # Section 6: a cancelled flight is compensated unless the passenger was
        # told at least 14 days ahead. The amount is the full band figure --
        # the 50% reduction belongs to the DELAY provision and is keyed to when
        # an alternative flight landed, which for a cancellation with no
        # rebooking recorded has not happened.
        #
        # So the figure is stated and the one open fact is asked. The passenger
        # is the only person who knows when the airline told them.
        award = COMPENSATION[distance_band(flight.distance_km, BAND_1_KM, BAND_2_KM)]
        return _outcome(
            Verdict.LIKELY_ELIGIBLE,
            applies=True,
            award=award,
            open_question=OpenQuestion.CANCELLATION_NOTICE,
            reason=(
                f"{LABEL} covers this flight ({flight.route}), and it was cancelled. "
                f"{_describe_band(flight.distance_km, award)} That is payable unless "
                f"the airline told you at least 14 days beforehand, which is the one "
                f"thing only you can tell us."
            ),
        )

    departure_delay = flight.departure_delay_hours
    if departure_delay is None:
        # NO DEPARTURE TIME -- BUT THAT DOES NOT ALWAYS MEAN WE CANNOT ANSWER.
        #
        # This is the ordinary case for a flight INTO Ben Gurion, not an
        # oddity: the IAA board reports what happened at its own airport, so
        # an arrival has an arrival time and no departure time at all. The
        # law measures at departure, so the rule used to give up on every
        # single inbound flight.
        #
        # It does not have to. A departure delay cannot exceed the arrival
        # delay plus whatever time the aircraft made up in the air, and an
        # aircraft cannot make up eight hours. So when the arrival delay is
        # known and is far enough below the threshold that no plausible
        # recovery could close the gap, the answer is a confident no.
        #
        # 6H502 from Heraklion on 1 October landed SIX MINUTES EARLY and was
        # still sent for manual review, because the board had no departure
        # time for it. For that to have been an eight-hour departure delay,
        # the aircraft would have had to make up eight hours on a 971 km
        # flight.
        #
        # Only ever turns "ask a person" into "no". A flight close enough to
        # the threshold that recovery could matter still goes to review, so
        # the one failure this system exists to avoid -- a wrong no -- is not
        # reachable from here.
        arrival_delay = flight.arrival_delay_hours

        # THE SAME INEQUALITY, READ THE OTHER WAY.
        #
        # A departure delay is the arrival delay plus whatever was made up in
        # the air, MINUS whatever was lost in it. The first direction (below)
        # rules a claim out. This one rules it in: a flight that reached Tel
        # Aviv eight hours late did not leave on time, because nobody loses
        # eight hours between two airports.
        #
        # 82 flights in the archive sat in manual review on this, and they
        # are not marginal -- WZ4311 from Sochi on 26 September arrived
        # NINETEEN HOURS late and we were telling its passengers we would
        # have to look into it by hand.
        #
        # The verdict is LIKELY_ELIGIBLE and not ELIGIBLE, deliberately. We
        # are not asserting the departure delay; we are saying this is a
        # claim and naming the one fact that settles it. The passenger was
        # in the departure hall and knows what time the aircraft left.
        #
        # The threshold is the law's own eight hours, with no second
        # constant. Below it the arithmetic genuinely does not decide -- a
        # flight that landed six hours late could have left four hours late
        # or nine -- so those still go to a person.
        if (
            arrival_delay is not None
            and arrival_delay >= MINIMUM_DEPARTURE_DELAY_HOURS
        ):
            band = distance_band(flight.distance_km, BAND_1_KM, BAND_2_KM)
            award = COMPENSATION[band]
            return _outcome(
                Verdict.LIKELY_ELIGIBLE,
                applies=True,
                award=award,
                open_question=OpenQuestion.ACTUAL_DEPARTURE,
                reason=(
                    f"{LABEL} covers this flight ({flight.route}), and it "
                    f"arrived {describe_delay(arrival_delay)}. This law "
                    f"measures the delay at departure, and the Israeli "
                    f"airport authority only records the Ben Gurion end, so "
                    f"we have no departure time for it -- but a flight does "
                    f"not lose "
                    f"{format_hours(MINIMUM_DEPARTURE_DELAY_HOURS)} in the "
                    f"air, so it left late too. "
                    f"{_describe_band(flight.distance_km, award)} Tell us "
                    f"what time you actually took off and we will confirm it."
                ),
            )

        if (
            arrival_delay is not None
            and arrival_delay + MAX_TIME_MADE_UP_HOURS
            < MINIMUM_DEPARTURE_DELAY_HOURS
        ):
            return _outcome(
                Verdict.NOT_ELIGIBLE,
                applies=True,
                reason=(
                    f"{LABEL} covers this flight, and it measures the delay at "
                    f"departure. We have no departure time for it -- the Israeli "
                    f"airport authority records what happens at Ben Gurion, and "
                    f"this flight departed elsewhere. It arrived "
                    f"{describe_delay(arrival_delay)}, though, and no aircraft "
                    f"makes up the "
                    f"{format_hours(MINIMUM_DEPARTURE_DELAY_HOURS)} that would "
                    f"have to be made up for this to be a claim."
                ),
            )
        return _review(
            "the flight has no recorded departure time, so the delay cannot be "
            "measured"
        )

    if departure_delay < MINIMUM_DEPARTURE_DELAY_HOURS:
        return _outcome(
            Verdict.NOT_ELIGIBLE,
            applies=True,
            reason=(
                f"{LABEL} covers this flight, but it departed "
                f"{describe_delay(departure_delay)}, below the "
                f"{format_hours(MINIMUM_DEPARTURE_DELAY_HOURS)} threshold. Note that "
                f"this law measures the delay at departure, not at arrival."
            ),
        )

    # Eligible on the departure delay -- but the amount turns on the arrival
    # delay, and without it we can say "yes" and not yet "exactly how much".
    #
    # The full band figure is quoted, not the halved one. The reduction applies
    # only when the airline still landed the passenger within a few hours of
    # schedule, which is the airline's defence to raise, not our assumption to
    # make against the passenger. Quoting the reduced amount would mean
    # under-stating every such claim by half on the strength of a fact nobody
    # has established.
    #
    # And the missing fact is not a mystery: the passenger was on the aircraft
    # and knows when it landed. So this is a question for them, with the amount
    # attached, rather than a blank referral that reads as a no.
    arrival_delay = flight.arrival_delay_hours
    if arrival_delay is None:
        band = distance_band(flight.distance_km, BAND_1_KM, BAND_2_KM)
        award = COMPENSATION[band]
        ceiling = REDUCTION_ARRIVAL_CEILING_HOURS[band]
        return _outcome(
            Verdict.LIKELY_ELIGIBLE,
            applies=True,
            award=award,
            open_question=OpenQuestion.ACTUAL_ARRIVAL,
            reason=(
                f"{LABEL} covers this flight ({flight.route}). It departed "
                f"{format_hours(departure_delay)} late, at or over the "
                f"{format_hours(MINIMUM_DEPARTURE_DELAY_HOURS)} threshold, so a claim "
                f"is owed. {_describe_band(flight.distance_km, award)} We have no "
                f"recorded landing time for it: if you did in fact arrive within "
                f"{format_hours(ceiling)} of the original schedule, the law halves "
                f"that amount. Tell us when you landed and we will confirm it."
            ),
        )

    award = compensation_for(flight.distance_km, arrival_delay)
    return _outcome(
        Verdict.ELIGIBLE,
        applies=True,
        award=award,
        reason=(
            f"{LABEL} covers this flight ({flight.route}). It departed "
            f"{format_hours(departure_delay)} late, at or over the "
            f"{format_hours(MINIMUM_DEPARTURE_DELAY_HOURS)} threshold. "
            f"{_describe_amount(flight.distance_km, arrival_delay, award)}"
        ),
    )


def _describe_amount(distance_km: float, arrival_delay: float, award: Money) -> str:
    band = distance_band(distance_km, BAND_1_KM, BAND_2_KM)
    full = COMPENSATION[band]
    where = (
        f"The distance of {distance_km:,.0f} km is {BAND_1_KM:,.0f} km or less",
        f"The distance of {distance_km:,.0f} km is between {BAND_1_KM:,.0f} and "
        f"{BAND_2_KM:,.0f} km",
        f"The distance of {distance_km:,.0f} km is over {BAND_2_KM:,.0f} km",
    )[band]

    if award != full:
        ceiling = REDUCTION_ARRIVAL_CEILING_HOURS[band]
        return (
            f"{where}, giving {full}, halved to {award} because you still landed "
            f"{format_hours(arrival_delay)} late, within the "
            f"{format_hours(ceiling)} the law allows for this distance."
        )
    return f"{where}, giving {award}."


def _outcome(
    verdict: Verdict,
    *,
    applies: bool,
    reason: str,
    award: Money | None = None,
    open_question: str | None = None,
) -> RegulationOutcome:
    return RegulationOutcome(
        regulation=CODE,
        verdict=verdict,
        reason=reason,
        applies=applies,
        award=award,
        open_question=open_question,
    )


def _describe_band(distance_km: float, award: Money) -> str:
    """Which distance band this flight falls in, and what it pays."""
    band = distance_band(distance_km, BAND_1_KM, BAND_2_KM)
    where = (
        f"The distance of {distance_km:,.0f} km is {BAND_1_KM:,.0f} km or less",
        f"The distance of {distance_km:,.0f} km is between {BAND_1_KM:,.0f} and "
        f"{BAND_2_KM:,.0f} km",
        f"The distance of {distance_km:,.0f} km is over {BAND_2_KM:,.0f} km",
    )[band]
    return f"{where}, giving {award}."


def _review(detail: str) -> RegulationOutcome:
    return _outcome(
        Verdict.NEEDS_REVIEW,
        applies=True,
        reason=f"{LABEL} covers this flight, but {detail}.",
    )
