"""Remembering what a source already told us.

A wrapper, not a provider: it takes any `FlightDataProvider` and returns one
that answers from `flight_lookups` when it can, and from the wrapped source
when it cannot, recording the answer either way.

WHY THIS IS WORTH BUILDING
--------------------------
The obvious reason is money. Flight data is metered, and this product has a
shape that punishes that: one disrupted flight carries a hundred and eighty
passengers, and a cancellation is exactly the thing they tell each other about.
Without a cache, one answer gets bought once per passenger.

The reason that matters more is time. Every commercial feed has a horizon --
AeroDataBox reaches back a year at most, on any plan -- while a passenger can
claim for four years in Israel and six in the UK. No subscription closes that
gap. Writing down what we see, on the day we see it, is the only thing that
does. A row saved today is still an answer in 2030, and it is an answer nobody
can stop selling us.

WHAT MAY BE REUSED, AND WHAT MAY NOT
------------------------------------
The whole correctness of this module is one distinction: a flight that has
finished cannot change, and a flight that has not is a prediction.

    LANDED, CANCELLED, DIVERTED   -> settled. Keep forever.
    SCHEDULED, EN_ROUTE, UNKNOWN  -> still moving. Keep for minutes.

Serving a stored SCHEDULED row as though it were fact is how a flight that went
on to be six hours late gets reported as punctual -- a wrong "no" on a real
claim, which is the one failure this system is built to avoid. So a row is
reused only when it is settled, or when it is young enough that nothing can
have happened since.

An empty answer -- "no such flight" -- is stored too, because repeatedly
re-asking about a typo is how quota disappears. It is never treated as settled:
a flight missing from today's data can appear in tomorrow's when the schedule
is loaded.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any, Final

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import FlightLookup
from app.domain.models import FlightStatus
from app.observability import flow
from app.providers.base import FlightDataProvider, RawFlight
from app.providers.chain import ChainProvider

# A flight in one of these has happened. Nothing about it will change again.
SETTLED: Final = frozenset(
    {FlightStatus.LANDED, FlightStatus.CANCELLED, FlightStatus.DIVERTED}
)

# How long an unsettled answer may be served. Long enough to absorb the burst
# of people checking the same flight within a few minutes of each other, short
# enough that a flight cannot have landed in the meantime.
DEFAULT_TTL: Final = timedelta(minutes=15)

_TIMES: Final = (
    "scheduled_departure",
    "actual_departure",
    "scheduled_arrival",
    "actual_arrival",
)


class CachingProvider:
    """Wraps a provider with a remembered answer. Satisfies
    `FlightDataProvider`."""

    def __init__(
        self,
        inner: FlightDataProvider,
        session_factory: sessionmaker[Session],
        *,
        ttl: timedelta = DEFAULT_TTL,
    ) -> None:
        self._inner = inner
        self._sessions = session_factory
        self._ttl = ttl
        self.name = inner.name

    async def fetch(
        self, flight_number: str, flight_date: date
    ) -> Sequence[RawFlight]:
        number = flight_number.strip().upper()

        stored = self._read(number, flight_date)
        if stored is not None:
            row, usable = stored
            if usable:
                flow.line(
                    "← remembered",
                    f"{len(row.flights)} flight(s) · {self.name} · "
                    f"{'settled' if row.is_final else 'seen'} "
                    f"{_ago(row.observed_at)}",
                )
                return _decode(row.flights, self.name)

        flights = await self._inner.fetch(number, flight_date)
        self._write(number, flight_date, flights)
        return flights

    # --- storage ---

    def _read(
        self, number: str, flight_date: date
    ) -> tuple[FlightLookup, bool] | None:
        with self._sessions() as session:
            row = session.scalar(
                select(FlightLookup).where(
                    FlightLookup.provider == self.name,
                    FlightLookup.flight_number == number,
                    FlightLookup.flight_date == flight_date,
                )
            )
            if row is None:
                return None
            fresh = now() - row.observed_at < self._ttl
            # Detached from the session, so read what is needed first.
            session.expunge(row)
            return row, (row.is_final or fresh)

    def _write(
        self, number: str, flight_date: date, flights: Sequence[RawFlight]
    ) -> None:
        # A flight with no records is not settled -- see the module docstring.
        is_final = bool(flights) and all(f.status in SETTLED for f in flights)
        payload = [encode(f) for f in flights]

        with self._sessions() as session:
            row = session.scalar(
                select(FlightLookup).where(
                    FlightLookup.provider == self.name,
                    FlightLookup.flight_number == number,
                    FlightLookup.flight_date == flight_date,
                )
            )
            if row is None:
                session.add(
                    FlightLookup(
                        provider=self.name,
                        flight_number=number,
                        flight_date=flight_date,
                        observed_at=now(),
                        is_final=is_final,
                        flights=payload,
                    )
                )
            elif not row.is_final:
                # A settled row is never overwritten. It was true when it was
                # written and it cannot have become less true; a later, thinner
                # answer from a source that has begun to forget the flight must
                # not replace it.
                row.observed_at = now()
                row.is_final = is_final
                row.flights = payload
            session.commit()


def wrap_with_cache(
    provider: FlightDataProvider,
    session_factory: sessionmaker[Session],
    *,
    ttl: timedelta = DEFAULT_TTL,
) -> FlightDataProvider:
    """Cache each source, inside a chain rather than around it.

    Wrapping the chain as a whole would store rows under the name
    "chain(aerodatabox → iaa)", which answers a different question from the one
    the nightly archive answers -- the archive writes under "iaa", because the
    board is what said so. Two spellings of the same fact is one of them going
    unused.

    Wrapping each member also keeps the chain working: a cached miss on the
    paid feed still lets the free one be asked.
    """
    if isinstance(provider, ChainProvider):
        return ChainProvider(
            [wrap_with_cache(p, session_factory, ttl=ttl) for p in provider.providers]
        )
    return CachingProvider(provider, session_factory, ttl=ttl)


# --- turning a RawFlight into JSON and back ----------------------------------
#
# Written out by hand rather than pickled or dataclass-dumped, because these
# rows are meant to outlive the code that wrote them. A format that depends on
# the current class definition is a format that stops being readable the first
# time somebody renames a field, which for an archive is the whole loss.


def encode(flight: RawFlight) -> dict[str, Any]:
    record: dict[str, Any] = {
        "flight_number": flight.flight_number,
        "flight_date": flight.flight_date.isoformat(),
        "status": flight.status.value,
        "provider": flight.provider,
        "airline_iata": flight.airline_iata,
        "origin_iata": flight.origin_iata,
        "destination_iata": flight.destination_iata,
        "raw": dict(flight.raw),
    }
    for name in _TIMES:
        value: datetime | None = getattr(flight, name)
        record[name] = value.isoformat() if value else None
    return record


def _decode(payload: list[Any], provider: str) -> tuple[RawFlight, ...]:
    return tuple(_one(item, provider) for item in payload if isinstance(item, dict))


def _one(item: dict[str, Any], provider: str) -> RawFlight:
    times = {name: _time(item.get(name)) for name in _TIMES}
    return RawFlight(
        flight_number=str(item["flight_number"]),
        flight_date=date.fromisoformat(str(item["flight_date"])),
        # A status this code no longer recognises becomes UNKNOWN rather than
        # raising: an old row is still worth most of what it says, and UNKNOWN
        # sends it to a person instead of throwing it away.
        status=_status(item.get("status")),
        provider=provider,
        airline_iata=item.get("airline_iata"),
        origin_iata=item.get("origin_iata"),
        destination_iata=item.get("destination_iata"),
        raw=item.get("raw") or {},
        **times,
    )


def _status(value: Any) -> FlightStatus:
    try:
        return FlightStatus(str(value))
    except ValueError:
        return FlightStatus.UNKNOWN


def _time(value: Any) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(str(value))
    # Rows written before the column was timezone-aware, or by a source that
    # dropped the offset. UTC is the only thing this system ever stores.
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def now() -> datetime:
    return datetime.now(UTC)


def _ago(when: datetime) -> str:
    seconds = int((now() - when).total_seconds())
    if seconds < 90:
        return f"{seconds}s ago"
    if seconds < 5400:
        return f"{seconds // 60}m ago"
    if seconds < 172800:
        return f"{seconds // 3600}h ago"
    return f"{seconds // 86400}d ago"
