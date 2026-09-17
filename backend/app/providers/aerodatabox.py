"""AeroDataBox adapter.

Translates one vendor's JSON into `RawFlight`, and nothing else. Every design
decision above this file is unaffected by what happens inside it -- that is the
whole point of the port in `base.py`.

Endpoint:  GET /flights/number/{number}/{date}
Docs:      https://doc.aerodatabox.com/

Two quirks of this API are worth knowing before reading the parser:

1. Timestamps are NOT ISO 8601. They arrive as "2026-08-14 02:20Z" -- a space
   where the T belongs. `datetime.fromisoformat` rejects that, so times go
   through `_parse_time`.
2. Each movement carries several times. `scheduledTime` is the plan,
   `revisedTime` is the airline's updated estimate, and `runwayTime` is when the
   aircraft actually left or touched the ground. We prefer runwayTime and fall
   back to revisedTime, because an estimate is better than nothing but worse
   than a fact.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from typing import Any, Final

import httpx

from app.domain.models import FlightStatus
from app.providers.base import (
    ProviderAuthError,
    ProviderRateLimited,
    ProviderResponseInvalid,
    ProviderUnavailable,
    RawFlight,
)

DEFAULT_BASE_URL: Final = "https://aerodatabox.p.rapidapi.com"
DEFAULT_RAPIDAPI_HOST: Final = "aerodatabox.p.rapidapi.com"

# Generous enough for a slow upstream, short enough that a customer is not left
# staring at a spinner. Connect is tight because a slow connect means the host
# is in trouble; read is longer because the query itself can be slow.
DEFAULT_TIMEOUT: Final = httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0)

# Retries apply ONLY to failures that a retry can plausibly fix: a timeout, a
# dropped connection, a 5xx. Never to a 4xx -- asking again with the same bad
# key or the same unknown flight number just spends quota.
DEFAULT_MAX_ATTEMPTS: Final = 3
DEFAULT_BACKOFF_SECONDS: Final = 0.5

# AeroDataBox's flight status vocabulary, mapped onto ours.
#
# Anything absent from this table becomes UNKNOWN, which becomes NEEDS_REVIEW
# upstream. That is deliberate: if the vendor adds a status we have never seen,
# the right response is to ask a human, not to guess which bucket it belongs in.
_STATUS: Final[Mapping[str, FlightStatus]] = {
    "arrived": FlightStatus.LANDED,
    "departed": FlightStatus.EN_ROUTE,
    "enroute": FlightStatus.EN_ROUTE,
    "approaching": FlightStatus.EN_ROUTE,
    "expected": FlightStatus.SCHEDULED,
    "scheduled": FlightStatus.SCHEDULED,
    "checkin": FlightStatus.SCHEDULED,
    "boarding": FlightStatus.SCHEDULED,
    "gateclosed": FlightStatus.SCHEDULED,
    "delayed": FlightStatus.SCHEDULED,
    "canceled": FlightStatus.CANCELLED,
    "cancelled": FlightStatus.CANCELLED,
    "diverted": FlightStatus.DIVERTED,
    # "CanceledUncertain" means the vendor thinks it was cancelled but will not
    # commit. We do not commit either: UNKNOWN sends it to a person.
    "canceleduncertain": FlightStatus.UNKNOWN,
    "unknown": FlightStatus.UNKNOWN,
}


class AeroDataBoxProvider:
    """Fetches flight data from AeroDataBox. Satisfies `FlightDataProvider`."""

    name = "aerodatabox"

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        rapidapi_host: str = DEFAULT_RAPIDAPI_HOST,
        client: httpx.AsyncClient | None = None,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
    ) -> None:
        if not api_key or not api_key.strip():
            # Fail here rather than letting the vendor return 401 later. A
            # missing key is a configuration mistake, and naming it at
            # construction is far cheaper to diagnose than at request time.
            raise ProviderAuthError(
                "aerodatabox: no API key configured. Set AERODATABOX_API_KEY, "
                "or select the 'fake' provider to run without one."
            )
        self._api_key = api_key.strip()
        self._base_url = base_url.rstrip("/")
        self._rapidapi_host = rapidapi_host
        self._client = client
        self._max_attempts = max_attempts
        self._backoff_seconds = backoff_seconds

    async def fetch(
        self, flight_number: str, flight_date: date
    ) -> Sequence[RawFlight]:
        number = flight_number.strip().upper()
        path = f"/flights/number/{number}/{flight_date.isoformat()}"
        payload = await self._get(path)

        if payload is None:
            return ()  # no such flight -- an answer, not a failure

        if not isinstance(payload, list):
            raise ProviderResponseInvalid(
                f"aerodatabox: expected a list of flights for {number}, got "
                f"{type(payload).__name__}"
            )

        return tuple(
            _to_raw_flight(item, number, flight_date, self.name)
            for item in payload
            if isinstance(item, dict)
        )

    # --- HTTP ---

    async def _get(self, path: str) -> Any:
        """Perform the request, retrying only what a retry can fix.

        Returns the decoded body, or None when the vendor says there is no such
        flight.
        """
        last_error: Exception | None = None

        for attempt in range(1, self._max_attempts + 1):
            try:
                response = await self._request(path)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                await self._pause_before_retry(attempt)
                continue

            # 4xx: a retry changes nothing, so classify and raise immediately.
            if response.status_code in (401, 403):
                raise ProviderAuthError(
                    f"aerodatabox: rejected the API key ({response.status_code}). "
                    "On RapidAPI this usually means the account is not subscribed "
                    "to the AeroDataBox API, even when the key itself is valid."
                )
            if response.status_code == 429:
                raise ProviderRateLimited(
                    "aerodatabox: quota exhausted (429). Retrying will not help "
                    "until the quota resets."
                )
            if response.status_code in (204, 404):
                return None
            if response.status_code >= 500:
                last_error = ProviderUnavailable(
                    f"aerodatabox: upstream returned {response.status_code}"
                )
                await self._pause_before_retry(attempt)
                continue
            if response.status_code != 200:
                raise ProviderResponseInvalid(
                    f"aerodatabox: unexpected status {response.status_code}"
                )

            try:
                return response.json()
            except ValueError as exc:
                raise ProviderResponseInvalid(
                    "aerodatabox: response body was not valid JSON"
                ) from exc

        raise ProviderUnavailable(
            f"aerodatabox: gave up after {self._max_attempts} attempts "
            f"({last_error})"
        ) from last_error

    async def _request(self, path: str) -> httpx.Response:
        headers = {
            "X-RapidAPI-Key": self._api_key,
            "X-RapidAPI-Host": self._rapidapi_host,
            "Accept": "application/json",
        }
        params = {
            # Everything we do not need is everything we do not pay to transfer
            # or have to parse. Compensation needs times, airports and status.
            "withAircraftImage": "false",
            "withLocation": "false",
        }
        if self._client is not None:
            return await self._client.get(
                f"{self._base_url}{path}", headers=headers, params=params
            )
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            return await client.get(
                f"{self._base_url}{path}", headers=headers, params=params
            )

    async def _pause_before_retry(self, attempt: int) -> None:
        """Exponential backoff, skipped after the final attempt.

        Hammering an upstream that is already struggling makes it worse, and a
        fixed delay from many clients at once just re-synchronises the stampede.
        """
        if attempt < self._max_attempts:
            await asyncio.sleep(self._backoff_seconds * (2 ** (attempt - 1)))


# --- Translation -------------------------------------------------------------


def _to_raw_flight(
    item: Mapping[str, Any], number: str, flight_date: date, provider: str
) -> RawFlight:
    departure = _movement(item, "departure")
    arrival = _movement(item, "arrival")

    return RawFlight(
        flight_number=number,
        flight_date=flight_date,
        status=_status(item.get("status")),
        provider=provider,
        airline_iata=_code(item.get("airline"), "iata"),
        origin_iata=_code(departure.get("airport"), "iata"),
        destination_iata=_code(arrival.get("airport"), "iata"),
        scheduled_departure=_time(departure, "scheduledTime"),
        actual_departure=_actual(departure),
        scheduled_arrival=_time(arrival, "scheduledTime"),
        actual_arrival=_actual(arrival),
        raw=dict(item),
    )


def _movement(item: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = item.get(key)
    return value if isinstance(value, Mapping) else {}


def _actual(movement: Mapping[str, Any]) -> datetime | None:
    """The best available "what really happened" time.

    runwayTime is the fact -- wheels up, or wheels down. revisedTime is the
    airline's latest estimate. Preferring the fact and falling back to the
    estimate is the right order; inventing one from scheduledTime would turn a
    missing measurement into a confident zero delay.
    """
    return _time(movement, "runwayTime") or _time(movement, "revisedTime")


def _time(movement: Mapping[str, Any], key: str) -> datetime | None:
    block = movement.get(key)
    if not isinstance(block, Mapping):
        return None
    # `utc` is preferred over `local` for the obvious reason: `local` carries an
    # offset we would have to trust, while `utc` is already the answer.
    return _parse_time(block.get("utc")) or _parse_time(block.get("local"))


_TRAILING_Z = re.compile(r"[zZ]$")


def _parse_time(value: Any) -> datetime | None:
    """Parse AeroDataBox's not-quite-ISO timestamps.

    They arrive as "2026-08-14 02:20Z" or "2026-08-14 05:20+03:00" -- a space
    where ISO 8601 puts a T, and sometimes no seconds. Returns None rather than
    raising on anything unrecognised, because one unparseable timestamp should
    become NEEDS_REVIEW downstream, not take out the whole response.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    text = _TRAILING_Z.sub("+00:00", value.strip().replace(" ", "T", 1))
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    # A timestamp with no offset at all is assumed UTC: this vendor's `utc`
    # field occasionally omits the Z, and treating it as local would be worse.
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _status(value: Any) -> FlightStatus:
    if not isinstance(value, str):
        return FlightStatus.UNKNOWN
    return _STATUS.get(value.strip().lower().replace(" ", ""), FlightStatus.UNKNOWN)


def _code(block: Any, key: str) -> str | None:
    if not isinstance(block, Mapping):
        return None
    value = block.get(key)
    return value.strip().upper() if isinstance(value, str) and value.strip() else None
