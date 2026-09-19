"""Several sources, asked in order, presented as one.

No single flight-data source is both complete and authoritative. A global
commercial feed carries both ends of a journey but has holes in any one
country's coverage; a national airport board is complete for its own airport and
knows only the movement that happened there. Choosing one means accepting the
other's failure mode permanently.

So the chain asks them in order and returns the first real answer.

WHAT COUNTS AS AN ANSWER
------------------------
Three outcomes, and keeping them apart is the entire job of this module:

    flights returned  -> an answer. Stop; later providers are not consulted.
    empty, no error   -> an answer: "we hold those days and it is not there."
    raised            -> NOT an answer. This provider could not look.

A provider that raises is skipped, not fatal, because the next one may hold the
flight -- that is why there is a chain at all. But if EVERY provider raised,
nobody looked, and the chain raises rather than returning empty. The difference
reaches the customer: empty becomes "check the flight number", while a raised
error becomes NEEDS_REVIEW. Turning "we could not look" into "it does not
exist" would tell somebody with a valid claim to go away, which is the one
failure this system is built to avoid.

ORDER MATTERS, AND IT IS CONFIGURATION
--------------------------------------
Put the source with the most complete records first and the cheapest one second,
or the other way around if quota is the binding constraint. Either is defensible
and neither is hardcoded.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from app.observability import flow
from app.providers.base import FlightDataError, FlightDataProvider, RawFlight


class ChainProvider:
    """Asks each provider in turn. Satisfies `FlightDataProvider`."""

    def __init__(self, providers: Sequence[FlightDataProvider]) -> None:
        if not providers:
            raise ValueError("a chain needs at least one provider")
        self._providers = tuple(providers)
        self.name = "chain(" + " → ".join(p.name for p in self._providers) + ")"

    async def fetch(
        self, flight_number: str, flight_date: date
    ) -> Sequence[RawFlight]:
        errors: list[tuple[str, FlightDataError]] = []
        looked = False

        for provider in self._providers:
            try:
                flights = await provider.fetch(flight_number, flight_date)
            except FlightDataError as exc:
                # Recorded, not raised. The next source may hold it.
                errors.append((provider.name, exc))
                flow.line("provider", f"{provider.name} could not look — {exc}")
                continue

            looked = True
            if flights:
                return flights
            flow.line("provider", f"{provider.name} has no such flight")

        if looked:
            # At least one source genuinely looked and came back empty. That is
            # a real "no such flight", and the customer can act on it.
            return ()

        # Nobody could look. Report the first failure: it is the one from the
        # provider the operator chose to trust first.
        raise errors[0][1]
