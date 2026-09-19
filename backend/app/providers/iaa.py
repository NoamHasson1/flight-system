"""Israel Airports Authority adapter -- the Ben Gurion board.

The official record of what happened at TLV, published by the state on
data.gov.il. No key, no quota, no vendor.

Endpoint:  GET https://data.gov.il/api/3/action/datastore_search
Dataset:   "Flights from and to Ben Gurion Airport" (CKAN datastore)

WHY THIS EXISTS ALONGSIDE AERODATABOX
-------------------------------------
A commercial global feed and a national airport board fail in opposite
directions, so neither alone is enough.

The global feed carries both ends of every journey -- departure AND arrival
times -- which is what EC261 and UK261 need, because they measure the delay at
arrival. But its Tel Aviv coverage has holes: a full day of TLV departures came
back with 162 flights and ZERO cancellations, which is not a quiet day, it is a
feed that drops them. Charter carriers go missing entirely.

This board is the opposite. It is authoritative and complete for Tel Aviv,
cancellations included, and it costs nothing. But each record describes only the
movement AT Ben Gurion: a departure row knows when the aircraft left and nothing
about when it landed. So it can settle an Israeli-law question on its own, where
the threshold is measured at departure, and usually cannot settle an EC261 one.

Hence the chain in `chain.py` rather than a replacement.

THREE THINGS THIS FEED WILL DO TO YOU
-------------------------------------
1. `CHPTOL` IS NOT AN ACTUAL TIME. It is "the current best time" -- an estimate
   for a flight that has not moved yet, and a fact only once the board says
   DEPARTED or LANDED. A future flight carries CHPTOL == CHSTOL, which reads as
   a perfectly punctual flight that has not happened. Treating it as an actual
   would manufacture on-time records for tomorrow's schedule, so only the two
   settled statuses produce an actual time here.

2. FLIGHT NUMBERS ARE ZERO-PADDED, inconsistently. El Al 16 is stored as "016",
   and a filtered query for "16" matches nothing at all. Numbers are therefore
   compared as integers, never as strings.

3. TIMES ARE LOCAL AND NAIVE -- no offset, no zone, Israel time implied. Israel
   observes DST, so the offset is +2 or +3 depending on the date and cannot be
   hardcoded. They are converted here, at the edge, because RawFlight refuses
   naive datetimes and a naive/aware mix silently produces a wrong delay.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from typing import Any, Final
from zoneinfo import ZoneInfo

import httpx

from app.domain.models import FlightStatus
from app.observability import flow
from app.providers.base import (
    ProviderCoverageGap,
    ProviderResponseInvalid,
    ProviderUnavailable,
    RawFlight,
)

DEFAULT_BASE_URL: Final = "https://data.gov.il/api/3/action/datastore_search"

# The Ben Gurion flights dataset on data.gov.il.
DEFAULT_RESOURCE_ID: Final = "e83f763b-b7d7-479e-b172-ae981ddc6de5"

# Every record in this dataset is one end of a journey through this airport.
BEN_GURION: Final = "TLV"

ISRAEL: Final = ZoneInfo("Asia/Jerusalem")

DEFAULT_TIMEOUT: Final = httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0)

# One airline's flights across the board's whole window. Comfortably above the
# busiest carrier at TLV, so a truncated page can never silently drop the
# flight being asked about.
_PAGE_SIZE: Final = 32000

# The board's status vocabulary, mapped onto ours.
#
# Anything absent becomes UNKNOWN, which becomes NEEDS_REVIEW upstream: a status
# we have never seen is a question for a person, not a guess.
_STATUS: Final[Mapping[str, FlightStatus]] = {
    "DEPARTED": FlightStatus.EN_ROUTE,
    "LANDED": FlightStatus.LANDED,
    "LANDING": FlightStatus.EN_ROUTE,
    "CANCELED": FlightStatus.CANCELLED,
    # Everything below is a flight that has not moved yet. "FINAL" and "NOT
    # FINAL" describe whether the GATE is final, not the flight -- an easy and
    # expensive thing to misread.
    "ON TIME": FlightStatus.SCHEDULED,
    "DELAYED": FlightStatus.SCHEDULED,
    "FINAL": FlightStatus.SCHEDULED,
    "NOT FINAL": FlightStatus.SCHEDULED,
}

# The only two statuses where the board is reporting a fact rather than a plan.
_SETTLED: Final = frozenset({"DEPARTED", "LANDED"})


class IsraelAirportsProvider:
    """Fetches flight data from the Ben Gurion board. Satisfies
    `FlightDataProvider`."""

    name = "iaa"

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        resource_id: str = DEFAULT_RESOURCE_ID,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url
        self._resource_id = resource_id
        self._client = client

    async def fetch(
        self, flight_number: str, flight_date: date
    ) -> Sequence[RawFlight]:
        airline, digits = _split(flight_number)
        if airline is None or digits is None:
            # Not a flight number this board could hold. Not a failure: the
            # caller asked, and the honest answer is that there is nothing here.
            flow.line("← board", f"{flight_number} is not a recognisable number")
            return ()

        flow.line("→ GET", f"{self._base_url} · {airline} (Ben Gurion board)")

        # Filtered by airline only, then matched on the number here, because the
        # stored numbers are zero-padded and string equality misses them.
        records = await self._query({"CHOPER": airline})

        window = _window(records)
        matches = [r for r in records if _same_number(r, digits)]
        on_date = [r for r in matches if _local_date(r) == flight_date]

        if on_date:
            flights = tuple(
                _to_raw_flight(r, flight_number, flight_date, self.name)
                for r in on_date
            )
            flow.line("← board", f"{len(flights)} flight(s)")
            for item in flights:
                flow.cont(
                    f"{item.route}  {item.airline_iata or '??'}  {item.status.value}"
                )
                flow.cont(
                    f"  scheduled  dep {_at(item.scheduled_departure)}  "
                    f"arr {_at(item.scheduled_arrival)}"
                )
                flow.cont(
                    f"  actual     dep {_at(item.actual_departure)}  "
                    f"arr {_at(item.actual_arrival)}"
                )
            return flights

        # Nothing on that date. Before calling it "no such flight", check
        # whether the date was even within reach: this board is a rolling window
        # of a few days around today, and reporting a flight from last month as
        # non-existent would be a confident lie about data we never had.
        if window and not (window[0] <= flight_date <= window[1]):
            flow.line(
                "← board",
                f"outside the published window {window[0]} … {window[1]}",
            )
            raise ProviderCoverageGap(
                f"iaa: the Ben Gurion board publishes "
                f"{window[0].isoformat()} to {window[1].isoformat()}; "
                f"{flight_date.isoformat()} is outside it."
            )

        flow.line("← board", "no such flight")
        return ()

    async def snapshot(self) -> Sequence[RawFlight]:
        """Every flight currently on the board, as one list.

        For the archive rather than for a check. The board publishes a rolling
        few days and then forgets; this is how those days stop being rolling.
        """
        records = await self._query({})
        flights: list[RawFlight] = []
        for record in records:
            airline = str(record.get("CHOPER") or "").strip().upper()
            digits = str(record.get("CHFLTN") or "").strip()
            local = _local_date(record)
            if not airline or not digits.isdigit() or local is None:
                continue
            # Stripped of padding so the stored number matches what a customer
            # types. "016" is how the board writes it; nobody writes it that
            # way on a claim form.
            number = f"{airline}{int(digits)}"
            flights.append(_to_raw_flight(record, number, local, self.name))
        return flights

    # --- HTTP ---

    async def _query(self, filters: Mapping[str, str]) -> list[dict[str, Any]]:
        params = {
            "resource_id": self._resource_id,
            "limit": str(_PAGE_SIZE),
        }
        if filters:
            params["filters"] = json.dumps(dict(filters))
        try:
            if self._client is not None:
                response = await self._client.get(self._base_url, params=params)
            else:
                async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                    response = await client.get(self._base_url, params=params)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise ProviderUnavailable(f"iaa: could not reach data.gov.il ({exc})")

        if response.status_code != 200:
            raise ProviderUnavailable(
                f"iaa: data.gov.il returned {response.status_code}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderResponseInvalid(f"iaa: response was not JSON ({exc})")

        if not isinstance(payload, dict) or not payload.get("success"):
            raise ProviderResponseInvalid("iaa: the dataset query was refused")

        records = (payload.get("result") or {}).get("records")
        if not isinstance(records, list):
            raise ProviderResponseInvalid(
                "iaa: expected result.records to be a list"
            )
        return [r for r in records if isinstance(r, dict)]


# --- Translation -------------------------------------------------------------


def _split(flight_number: str) -> tuple[str | None, int | None]:
    """"LY 315" -> ("LY", 315). Anything unparsable -> (None, None)."""
    compact = "".join(flight_number.split()).upper()
    head = compact[:2]
    tail = compact[2:]
    if len(head) != 2 or not head.isalnum() or not tail.isdigit():
        return None, None
    return head, int(tail)


def _same_number(record: Mapping[str, Any], digits: int) -> bool:
    raw = str(record.get("CHFLTN") or "").strip()
    return raw.isdigit() and int(raw) == digits


def _local_date(record: Mapping[str, Any]) -> date | None:
    stamp = _parse_local(record.get("CHSTOL"))
    if stamp is None:
        return None
    return stamp.astimezone(ISRAEL).date()


def _window(records: Sequence[Mapping[str, Any]]) -> tuple[date, date] | None:
    """The span of dates this response actually covers."""
    dates = [d for d in (_local_date(r) for r in records) if d is not None]
    return (min(dates), max(dates)) if dates else None


def _parse_local(value: Any) -> datetime | None:
    """Israel-local, naive, "2026-09-19T08:00:00" -> aware UTC.

    The zone does the DST arithmetic. Israel switches in March and October, so
    a flight in July and a flight in December sit on different offsets and a
    fixed +02:00 or +03:00 would be wrong for half the year.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        naive = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    if naive.tzinfo is not None:
        return naive.astimezone(UTC)
    return naive.replace(tzinfo=ISRAEL).astimezone(UTC)


def _to_raw_flight(
    record: Mapping[str, Any],
    flight_number: str,
    flight_date: date,
    provider: str,
) -> RawFlight:
    raw_status = str(record.get("CHRMINE") or "").strip().upper()
    status = _STATUS.get(raw_status, FlightStatus.UNKNOWN)

    scheduled = _parse_local(record.get("CHSTOL"))
    # Only a settled flight has a real time. See quirk 1 in the module docstring.
    actual = _parse_local(record.get("CHPTOL")) if raw_status in _SETTLED else None

    other = str(record.get("CHLOC1") or "").strip().upper() or None
    departing = str(record.get("CHAORD") or "").strip().upper() == "D"

    return RawFlight(
        flight_number=flight_number.strip().upper(),
        flight_date=flight_date,
        status=status,
        provider=provider,
        airline_iata=str(record.get("CHOPER") or "").strip().upper() or None,
        origin_iata=BEN_GURION if departing else other,
        destination_iata=other if departing else BEN_GURION,
        # One end only. Which end depends on the direction, and the half we do
        # not have stays None rather than being invented -- the mapper decides
        # what a missing time means, and it decides NEEDS_REVIEW.
        scheduled_departure=scheduled if departing else None,
        actual_departure=actual if departing else None,
        scheduled_arrival=None if departing else scheduled,
        actual_arrival=None if departing else actual,
        raw=dict(record),
    )


def _at(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d %H:%MZ") if value else "—"
