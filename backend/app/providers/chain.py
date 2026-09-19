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


def is_usable(flights: Sequence[RawFlight]) -> bool:
    """True when every record could actually answer the question.

    Two ways a source returns a flight that cannot be used, both seen in
    production within an hour of each other:

    NO ROUTE. A codeshare record with a full departure airport and an arrival
    that is only a name. Without both ends there is no country pair, so no law
    can be tested, and no distance, so no amount can be computed.

    IMPOSSIBLE TIMES. A scheduled arrival BEFORE the scheduled departure. Real
    example: IZ216 on 14 September came back with a departure scheduled 15 Sep
    00:25 local and an arrival scheduled 14 Sep 03:35 local. One of those is
    wrong and the record cannot say which -- so a departure delay computed from
    it is off by twenty-two hours, in the direction that denies a real claim.

    Neither is a judgement about the law; both are a judgement about whether
    the record is coherent, which is this layer's business. Asking the next
    source is exactly what a chain is for, and the Ben Gurion board carries a
    correct arrival time for that flight.
    """
    return all(
        f.origin_iata
        and f.destination_iata
        and _times_agree(f)
        for f in flights
    )


def _times_agree(flight: RawFlight) -> bool:
    """False when the record contradicts itself about when the flight was."""
    pairs = (
        (flight.scheduled_departure, flight.scheduled_arrival),
        (flight.actual_departure, flight.actual_arrival),
    )
    return all(
        departure is None or arrival is None or arrival > departure
        for departure, arrival in pairs
    )


class ChainProvider:
    """Asks each provider in turn. Satisfies `FlightDataProvider`."""

    def __init__(self, providers: Sequence[FlightDataProvider]) -> None:
        if not providers:
            raise ValueError("a chain needs at least one provider")
        self._providers = tuple(providers)
        self.name = "chain(" + " → ".join(p.name for p in self._providers) + ")"

    @property
    def providers(self) -> tuple[FlightDataProvider, ...]:
        """The members, in the order they are asked."""
        return self._providers

    async def fetch(
        self, flight_number: str, flight_date: date
    ) -> Sequence[RawFlight]:
        errors: list[tuple[str, FlightDataError]] = []
        looked = False
        partial: Sequence[RawFlight] | None = None

        for provider in self._providers:
            try:
                flights = await provider.fetch(flight_number, flight_date)
            except FlightDataError as exc:
                # Recorded, not raised. The next source may hold it.
                errors.append((provider.name, exc))
                flow.line("provider", f"{provider.name} could not look — {exc}")
                continue

            looked = True
            if not flights:
                flow.line("provider", f"{provider.name} has no such flight")
                continue

            if is_usable(flights):
                return flights

            # Found, but incoherent -- see `_usable`. Keeping the FIRST such
            # answer and asking the next source is the point of having sources
            # that fail differently: the board carries a proper destination
            # code for the flights the commercial feed abbreviates, and a
            # correct arrival time for the ones it mis-dates.
            if partial is None:
                partial = flights
            flow.line(
                "provider",
                f"{provider.name} has it but the record does not hold together "
                f"— trying the next",
            )

        if partial is not None:
            # Nobody did better. Return what we have rather than nothing: the
            # mapper's complaint about a missing airport is a more useful thing
            # to show than "no such flight".
            return partial

        if looked:
            # At least one source genuinely looked and came back empty. That is
            # a real "no such flight", and the customer can act on it.
            return ()

        # Nobody could look. Report the first failure: it is the one from the
        # provider the operator chose to trust first.
        raise errors[0][1]
