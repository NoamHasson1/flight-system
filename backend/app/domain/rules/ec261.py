"""EC261 -- Regulation (EC) No 261/2004.

This file is the numbers. The flow they drive lives in
`base.ArrivalDelayRegulation`, shared with UK261, which is the same regulation
retained in British law.

It mirrors section 5 of rules.md, in the same order:

    1. Does this law apply at all?    -> territories, carrier_states
    2. Was the disruption bad enough? -> minimum_arrival_delay_hours
    3. How much money is owed?        -> band_boundaries, compensation

When these figures change, exactly one file changes, and rules.md is updated to
match.
"""

from __future__ import annotations

from app.domain.models import Currency, Money
from app.domain.rules.base import (
    EC261_CARRIER_STATES,
    EC261_TERRITORIES,
    ArrivalDelayRegulation,
)

CODE = "EC261"
NAME = "Regulation (EC) No 261/2004"

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

REGULATION = ArrivalDelayRegulation(
    code=CODE,
    name=NAME,
    territories=EC261_TERRITORIES,
    carrier_states=EC261_CARRIER_STATES,
    jurisdiction_summary=(
        "The regulation covers flights leaving the EU/EEA on any airline, or "
        "arriving into the EU/EEA on an EU carrier."
    ),
    band_boundaries=(BAND_1_KM, BAND_2_KM),
    compensation=COMPENSATION,
    minimum_arrival_delay_hours=MINIMUM_ARRIVAL_DELAY_HOURS,
    long_haul_reduction_below_hours=LONG_HAUL_REDUCTION_BELOW_HOURS,
)

applies = REGULATION.applies
compensation_for = REGULATION.compensation_for
evaluate = REGULATION.evaluate
