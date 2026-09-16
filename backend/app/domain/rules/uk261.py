"""UK261 -- the Air Passenger Rights regulation retained in UK law.

At Brexit the United Kingdom copied Regulation (EC) 261/2004 into its own
statute book, changed the currency and changed "EU" to "UK". Everything else --
the three-hour threshold, the 1,500/3,500 km bands, the long-haul reduction --
is identical, which is why the flow lives in `base.ArrivalDelayRegulation` and
this file is only the numbers.

Mirrors section 7 of rules.md.

The two laws are expected to diverge over time: the EU agreed a revision in June
2026 that the UK has not adopted. Keeping the constants in separate files means
that divergence costs one edit here, not a conditional inside a shared rule.
"""

from __future__ import annotations

from app.domain.models import Currency, Money
from app.domain.rules.base import (
    UK_CARRIER_STATES,
    UK_TERRITORIES,
    UK_UNSETTLED_TERRITORIES,
    ArrivalDelayRegulation,
)

CODE = "UK261"
NAME = "The Air Passenger Rights and Air Travel Organisers' Licensing "
"(Amendment) (EU Exit) Regulations 2019"

BAND_1_KM = 1500.0
BAND_2_KM = 3500.0
MINIMUM_ARRIVAL_DELAY_HOURS = 3.0

COMPENSATION: tuple[Money, Money, Money] = (
    Money.of("220", Currency.GBP),  # 1,500 km or less
    Money.of("350", Currency.GBP),  # 1,500 - 3,500 km
    Money.of("520", Currency.GBP),  # over 3,500 km
)

# The retained equivalent of Article 7(2)(c). Halves the top band to 260 pounds
# when the airline still lands the passenger within four hours.
LONG_HAUL_REDUCTION_BELOW_HOURS = 4.0

REGULATION = ArrivalDelayRegulation(
    code=CODE,
    name=NAME,
    territories=UK_TERRITORIES,
    carrier_states=UK_CARRIER_STATES,
    jurisdiction_summary=(
        "The regulation covers flights leaving the UK on any airline, or "
        "arriving into the UK on a UK or EU carrier."
    ),
    band_boundaries=(BAND_1_KM, BAND_2_KM),
    compensation=COMPENSATION,
    minimum_arrival_delay_hours=MINIMUM_ARRIVAL_DELAY_HOURS,
    long_haul_reduction_below_hours=LONG_HAUL_REDUCTION_BELOW_HOURS,
    unsettled_territories=UK_UNSETTLED_TERRITORIES,
)

applies = REGULATION.applies
compensation_for = REGULATION.compensation_for
evaluate = REGULATION.evaluate
