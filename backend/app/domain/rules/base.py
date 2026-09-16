"""Shared vocabulary for the three compensation regulations.

Each regulation is a module exposing `CODE`, `NAME` and an `evaluate` function.
There is no class hierarchy: a regulation is a pure function from FlightFacts to
a RegulationOutcome, and anything more elaborate would be ceremony.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.domain.models import FlightFacts, Money, Verdict

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
