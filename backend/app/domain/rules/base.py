"""Shared vocabulary for the three compensation regulations.

Each regulation is a module exposing `CODE`, `NAME` and an `evaluate` function.
There is no class hierarchy: a regulation is a pure function from FlightFacts to
a RegulationOutcome, and anything more elaborate would be ceremony.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.domain.models import FlightFacts, FlightStatus, Money, Verdict

# --- The result of applying one regulation to one flight ---------------------


@dataclass(frozen=True, slots=True)
class RegulationOutcome:
    """What one law has to say about one flight.

    `reason` is not decoration. It is shown to the customer, so it must be a
    complete sentence that explains the decision using the actual numbers. An
    unexplained "no" destroys trust; a "no" that says why is a good product.
    """

    regulation: str  # "EC261"
    verdict: Verdict
    reason: str
    applies: bool  # did this law cover the flight at all?
    award: Money | None = None

    def __post_init__(self) -> None:
        if self.verdict is Verdict.ELIGIBLE and self.award is None:
            raise ValueError(f"{self.regulation}: ELIGIBLE outcome must carry an award")
        if self.verdict is not Verdict.ELIGIBLE and self.award is not None:
            raise ValueError(
                f"{self.regulation}: only an ELIGIBLE outcome may carry an award"
            )


class RegulationEvaluator(Protocol):
    """The shape every regulation module's `evaluate` satisfies."""

    def __call__(self, flight: FlightFacts) -> RegulationOutcome: ...


# --- Jurisdictions -----------------------------------------------------------
#
# ISO 3166-1 alpha-2, matching the `country` column of app/data/airports.csv.

EU_MEMBER_STATES: frozenset[str] = frozenset(
    {
        "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR",
        "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK",
        "SI", "ES", "SE",
    }
)

# Non-EU members of the European Economic Area. EC261 applies here too.
# Liechtenstein has no airport of its own, but it can still license a carrier.
EEA_NON_EU: frozenset[str] = frozenset({"IS", "LI", "NO"})

# EU outermost regions (Art. 355(1) TFEU). These are legally *part of* the EU,
# but ISO gives them their own country codes, so `country in EU_MEMBER_STATES`
# would silently exclude them. Madeira and the Azores are already filed under
# PT, and the Canaries under ES, so they need no entry here.
EU_OUTERMOST_REGIONS: frozenset[str] = frozenset(
    {
        "GP",  # Guadeloupe
        "MQ",  # Martinique
        "GF",  # French Guiana
        "RE",  # Reunion
        "YT",  # Mayotte
        "MF",  # Saint-Martin (French part)
    }
)

# Deliberately NOT included: the Overseas Countries and Territories, which are
# associated with the EU but outside it -- New Caledonia (NC), French Polynesia
# (PF), Wallis and Futuna (WF), Saint-Pierre-et-Miquelon (PM),
# Saint-Barthelemy (BL, which left outermost-region status in 2012), Greenland
# (GL), the Faroes (FO) and the Dutch Caribbean (AW, CW, SX, BQ).

# Switzerland is in neither the EU nor the EEA, but applies EC261 through its
# bilateral air transport agreement with the EU, and Swiss carriers are treated
# as Community carriers for this purpose. Kept as its own constant so the
# reasoning stays visible and it can be removed in one line if that changes.
EC261_BY_BILATERAL_AGREEMENT: frozenset[str] = frozenset({"CH"})

EC261_TERRITORIES: frozenset[str] = (
    EU_MEMBER_STATES
    | EEA_NON_EU
    | EU_OUTERMOST_REGIONS
    | EC261_BY_BILATERAL_AGREEMENT
)

# The states whose carriers count as "Community carriers". Same set: a carrier
# licensed anywhere in the EU/EEA (or Switzerland) qualifies.
EC261_CARRIER_STATES: frozenset[str] = EC261_TERRITORIES


# --- Distance bands ----------------------------------------------------------


def distance_band(distance_km: float, first: float, second: float) -> int:
    """Return 0, 1 or 2 for the three compensation bands.

    All three regulations share this shape -- three bands split by two
    boundaries -- and differ only in where the boundaries sit (1,500/3,500 km
    for EC261 and UK261; 2,000/4,500 km for the Israeli law). Sharing the
    comparison means the "or less" / "more than" boundary handling is written
    once and tested once.

    The boundaries are inclusive at the bottom: a flight of exactly 1,500 km is
    "1,500 km or less", so it falls in band 0.
    """
    if distance_km <= first:
        return 0
    if distance_km <= second:
        return 1
    return 2


def format_hours(hours: float) -> str:
    """Render a delay the way a person says it: 4.25 -> "4h 15m".

    Reason strings are read by customers, and "4.25 hours" reads like a
    spreadsheet. Shared by all three regulations so they phrase it identically.
    """
    total_minutes = round(abs(hours) * 60)
    sign = "-" if hours < 0 else ""
    return f"{sign}{total_minutes // 60}h {total_minutes % 60:02d}m"


# --- United Kingdom ----------------------------------------------------------

UK_TERRITORIES: frozenset[str] = frozenset({"GB"})

# UK261 covers arrivals into the UK on UK carriers *and* on EU-licensed ones,
# so its carrier set is wider than its territory set.
UK_CARRIER_STATES: frozenset[str] = UK_TERRITORIES | EC261_CARRIER_STATES

# Crown Dependencies and Gibraltar. These are not part of the United Kingdom,
# and whether the retained regulation reaches them is genuinely unsettled rather
# than merely unresearched. Saying "no claim" here would be a confident answer we
# have not earned, so a route touching one of these goes to NEEDS_REVIEW.
UK_UNSETTLED_TERRITORIES: frozenset[str] = frozenset(
    {
        "GI",  # Gibraltar
        "JE",  # Jersey
        "GG",  # Guernsey / Alderney
        "IM",  # Isle of Man
    }
)


# --- The shared shape of EC261 and UK261 -------------------------------------


@dataclass(frozen=True, slots=True)
class ArrivalDelayRegulation:
    """EC261 and UK261, which are the same regulation with different numbers.

    UK261 is retained EU law: the United Kingdom copied Regulation 261/2004 into
    its own statute book at Brexit, changed the currency and changed "EU" to
    "UK". Writing the two out separately would duplicate every guard clause and
    every reason string, and a bug fixed in one would live on in the other.

    So the *flow* lives here, once, and each law is a declaration of its own
    constants. The Israeli law deliberately does not use this: it measures
    departure delay rather than arrival delay and reduces on a different rule,
    so forcing it into this shape would obscure a real difference rather than
    share a real similarity.
    """

    code: str
    name: str
    territories: frozenset[str]
    carrier_states: frozenset[str]
    jurisdiction_summary: str
    band_boundaries: tuple[float, float]
    compensation: tuple[Money, Money, Money]
    minimum_arrival_delay_hours: float
    unsettled_territories: frozenset[str] = frozenset()

    # How far below the threshold still counts as "too close to call".
    #
    # The Court of Justice held in Germanwings (C-452/13) that "arrival time"
    # means the moment a door opens and passengers may leave -- not the moment
    # the wheels touch the runway. Flight databases record touchdown, which
    # comes first, typically by five to fifteen minutes.
    #
    # So our arrival delay is systematically a little SHORT. A flight we measure
    # at 2h 50m may legally have arrived 3h 05m late, and answering "no" to that
    # passenger would be a wrong denial produced entirely by our instrumentation.
    #
    # Within this margin we decline to decide. The Israeli law deliberately does
    # not use one: its text keys off the "landing time", which is touchdown, so
    # there is no gap between what it asks and what we can measure.
    measurement_margin_hours: float = 0.25

    # --- 1. Does this law apply at all? ---

    def applies(self, flight: FlightFacts) -> bool:
        """Deliberately asymmetric, and the asymmetry is what people get wrong:

        * DEPARTING the territory covers *every* airline, wherever it is from.
        * ARRIVING into it only covers the regulation's own carriers.
        """
        departs_from = flight.origin_country in self.territories
        arrives_in = flight.destination_country in self.territories
        is_covered_carrier = flight.airline_country in self.carrier_states

        return departs_from or (arrives_in and is_covered_carrier)

    # --- 3. How much money is owed? ---

    def compensation_for(self, distance_km: float) -> Money:
        """The award for a flight of this distance.

        There is no 50% reduction here. Article 7(2), which allows one, opens
        with "when passengers are offered re-routing to their final destination
        on an alternative flight" -- it is about being rebooked after a
        cancellation, not about the flight you were on landing late. A delayed
        flight has no alternative flight, so the article does not reach it.

        The Israeli law is different: its reduction is written into the delay
        provision itself, so israel.py does implement one.
        """
        return self.compensation[distance_band(distance_km, *self.band_boundaries)]

    # --- Putting it together ---

    def evaluate(self, flight: FlightFacts) -> RegulationOutcome:
        unsettled = self.unsettled_territories & {
            flight.origin_country,
            flight.destination_country,
        }
        if unsettled:
            return self._review(
                f"the route touches {', '.join(sorted(unsettled))}, which is not part "
                f"of the territory {self.code} plainly covers. Whether the regulation "
                f"reaches it is unsettled, so this needs a person to look at"
            )

        if not self.applies(flight):
            return self._outcome(
                Verdict.NOT_ELIGIBLE,
                applies=False,
                reason=(
                    f"{self.code} does not cover this flight: it departs from "
                    f"{flight.origin_country} and arrives in "
                    f"{flight.destination_country}, and the operating carrier "
                    f"{flight.airline_iata} is licensed in {flight.airline_country}. "
                    f"{self.jurisdiction_summary}"
                ),
            )

        # From here the law applies, so every remaining answer is about this
        # flight's facts -- and anything we cannot establish becomes
        # NEEDS_REVIEW rather than a confident "no".

        if flight.status is FlightStatus.DIVERTED:
            return self._review("the flight was diverted, which needs a person to assess")

        if flight.status is FlightStatus.UNKNOWN:
            return self._review("we could not establish what happened to this flight")

        if flight.is_cancelled:
            # Cancellation compensation turns on how much notice the passenger
            # was given -- under 14 days and it is payable. No flight data API
            # reports that, and it is not ours to assume in either direction.
            return self._review(
                "the flight was cancelled. Compensation is payable when the airline "
                "gave less than 14 days' notice, which we need to confirm with you"
            )

        delay = flight.arrival_delay_hours
        if delay is None:
            return self._review(
                "the flight has no recorded arrival time yet, so the delay cannot "
                "be measured"
            )

        if self._too_close_to_call(delay):
            return self._review(
                f"it arrived {format_hours(delay)} late, just short of the "
                f"{format_hours(self.minimum_arrival_delay_hours)} threshold. "
                f"Flight databases record when the wheels touched down, but the "
                f"law counts from when the doors opened -- usually five to "
                f"fifteen minutes later. That difference could decide this claim, "
                f"so we will check it rather than turn you away"
            )

        if delay < self.minimum_arrival_delay_hours:
            return self._outcome(
                Verdict.NOT_ELIGIBLE,
                applies=True,
                reason=(
                    f"{self.code} covers this flight, but it arrived "
                    f"{format_hours(delay)} late, below the "
                    f"{format_hours(self.minimum_arrival_delay_hours)} threshold."
                ),
            )

        award = self.compensation_for(flight.distance_km)
        return self._outcome(
            Verdict.ELIGIBLE,
            applies=True,
            award=award,
            reason=(
                f"{self.code} covers this flight ({flight.route}). It arrived "
                f"{format_hours(delay)} late, at or over the "
                f"{format_hours(self.minimum_arrival_delay_hours)} threshold. "
                f"{self._describe_band(flight.distance_km, award)}"
            ),
        )

    def _too_close_to_call(self, delay: float) -> bool:
        """True when the delay sits inside the measurement margin below the
        threshold -- close enough that touchdown-versus-doors decides it."""
        floor = self.minimum_arrival_delay_hours - self.measurement_margin_hours
        return floor <= delay < self.minimum_arrival_delay_hours

    # --- reason-string helpers ---

    def _describe_band(self, distance_km: float, award: Money) -> str:
        band = distance_band(distance_km, *self.band_boundaries)
        first, second = self.band_boundaries
        descriptions = (
            f"The distance of {distance_km:,.0f} km is {first:,.0f} km or less",
            f"The distance of {distance_km:,.0f} km is between {first:,.0f} and "
            f"{second:,.0f} km",
            f"The distance of {distance_km:,.0f} km is over {second:,.0f} km",
        )
        return f"{descriptions[band]}, giving {award}."

    def _outcome(
        self,
        verdict: Verdict,
        *,
        applies: bool,
        reason: str,
        award: Money | None = None,
    ) -> RegulationOutcome:
        return RegulationOutcome(
            regulation=self.code,
            verdict=verdict,
            reason=reason,
            applies=applies,
            award=award,
        )

    def _review(self, detail: str) -> RegulationOutcome:
        return self._outcome(
            Verdict.NEEDS_REVIEW,
            applies=True,
            reason=f"{self.code} covers this flight, but {detail}.",
        )
