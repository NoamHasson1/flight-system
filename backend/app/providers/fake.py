"""A flight-data provider that answers from a script instead of the network.

It exists for three reasons, in order of importance:

1. **The test suite must never call a real API.** Doing so makes tests slow,
   flaky, dependent on somebody else's uptime, and -- on a metered plan -- it
   spends money on every CI run.
2. **The whole system can be built and demonstrated without an API key.**
   Everything above this layer is finished and provable before a single
   subscription exists.
3. **Failures can be summoned on demand.** Real providers fail rarely and
   inconveniently. Here, asking for flight ERR503 makes the provider go down,
   so every error path gets exercised deliberately rather than by luck.

The scenarios live in `fixtures/scenarios.json` and are vendor-neutral: they
describe flights in the shape of `RawFlight`, not in any vendor's JSON. That is
what lets them outlive a change of provider.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import date, datetime
from pathlib import Path
from typing import Any, Final

from app.domain.models import FlightStatus
from app.providers.base import (
    FlightDataError,
    ProviderAuthError,
    ProviderRateLimited,
    ProviderResponseInvalid,
    ProviderUnavailable,
    RawFlight,
)

_FIXTURES: Final = Path(__file__).resolve().parent / "fixtures" / "scenarios.json"

# A scenario may ask the provider to fail. Mapping the names rather than looking
# them up dynamically keeps the fixture file from being able to raise anything
# it likes.
_ERRORS: Final[dict[str, type[FlightDataError]]] = {
    "ProviderUnavailable": ProviderUnavailable,
    "ProviderRateLimited": ProviderRateLimited,
    "ProviderAuthError": ProviderAuthError,
    "ProviderResponseInvalid": ProviderResponseInvalid,
}

_ANY_DATE: Final = "*"


class FakeFlightProvider:
    """Serves scripted flights. Satisfies `FlightDataProvider`."""

    name = "fake"

    def __init__(self, scenarios_path: Path | None = None) -> None:
        self._path = scenarios_path or _FIXTURES
        self._scenarios = _load(self._path)

    async def fetch(
        self, flight_number: str, flight_date: date
    ) -> Sequence[RawFlight]:
        """Return the scripted flights for this number and date.

        Unknown combinations return an empty sequence -- "we looked and there is
        no such flight" -- which is the same answer a real provider gives and
        the same 404 the customer should see.
        """
        number = flight_number.strip().upper()
        scenario = self._scenarios.get((number, flight_date.isoformat()))
        if scenario is None:
            scenario = self._scenarios.get((number, _ANY_DATE))
        if scenario is None:
            # A tuple, like every other return from this method. Handing back a
            # list here and a tuple there invites callers to depend on the
            # difference, and the empty case is the one they handle least.
            return ()

        error = scenario.get("error")
        if error is not None:
            raise _ERRORS[error](
                f"{self.name}: simulated {error} for {number} "
                f"({scenario.get('description', '')})"
            )

        return tuple(
            _to_raw_flight(payload, number, flight_date, self.name)
            for payload in scenario.get("flights", [])
        )

    def describe(self) -> list[str]:
        """Every scenario, one line each. Used by the demo scripts and by
        anybody wondering what they can ask for."""
        seen: dict[tuple[str, str], str] = {}
        for (number, day), scenario in self._scenarios.items():
            seen[(number, day)] = scenario.get("description", "")
        return [f"{n} on {d}: {why}" for (n, d), why in sorted(seen.items())]


def _load(path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    document = json.loads(path.read_text(encoding="utf-8"))
    scenarios: dict[tuple[str, str], dict[str, Any]] = {}
    for scenario in document["scenarios"]:
        key = (scenario["flight_number"].upper(), scenario["date"])
        if key in scenarios:
            raise ValueError(f"{path.name}: duplicate scenario for {key}")
        if "error" in scenario and scenario["error"] not in _ERRORS:
            raise ValueError(
                f"{path.name}: scenario {key} raises unknown error "
                f"{scenario['error']!r}"
            )
        scenarios[key] = scenario
    return scenarios


def _to_raw_flight(
    payload: dict[str, Any], number: str, flight_date: date, provider: str
) -> RawFlight:
    return RawFlight(
        flight_number=number,
        flight_date=flight_date,
        status=FlightStatus(payload["status"]),
        provider=provider,
        airline_iata=payload.get("airline_iata"),
        origin_iata=payload.get("origin_iata"),
        destination_iata=payload.get("destination_iata"),
        scheduled_departure=_at(payload.get("scheduled_departure")),
        actual_departure=_at(payload.get("actual_departure")),
        scheduled_arrival=_at(payload.get("scheduled_arrival")),
        actual_arrival=_at(payload.get("actual_arrival")),
        raw=dict(payload),
    )


def _at(value: str | None) -> datetime | None:
    """Parse an ISO 8601 timestamp that must carry an offset.

    RawFlight would reject a naive datetime anyway; failing here names the
    fixture field that caused it.
    """
    if value is None:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError(f"scenario timestamp {value!r} has no UTC offset")
    return parsed
