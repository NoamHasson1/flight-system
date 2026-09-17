"""Record a real AeroDataBox response as a test fixture.

The fixtures in app/providers/fixtures/aerodatabox/ were written by hand from
the published schema, because no API key existed when the adapter was built.
This script replaces one with the genuine article.

    export AERODATABOX_API_KEY=...
    uv run python scripts/record_fixtures.py BA165 2026-08-14 arrived_delayed

Any difference between a hand-written fixture and the real response shows up
immediately as a failing parser test, which is a far better place to discover
schema drift than production.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.providers.aerodatabox import (  # noqa: E402
    DEFAULT_BASE_URL,
    DEFAULT_RAPIDAPI_HOST,
    AeroDataBoxProvider,
)
from app.providers.base import FlightDataError  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[1] / "app/providers/fixtures/aerodatabox"


async def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2

    number, day = sys.argv[1], date.fromisoformat(sys.argv[2])
    name = sys.argv[3] if len(sys.argv) > 3 else f"{number.lower()}_{day.isoformat()}"

    key = os.environ.get("AERODATABOX_API_KEY", "")
    if not key:
        print("AERODATABOX_API_KEY is not set.", file=sys.stderr)
        return 2

    # Go around the adapter's own parsing: a fixture is the RAW body, so that
    # the parser is what the tests exercise.
    import httpx

    url = f"{DEFAULT_BASE_URL}/flights/number/{number.upper()}/{day.isoformat()}"
    headers = {"X-RapidAPI-Key": key, "X-RapidAPI-Host": DEFAULT_RAPIDAPI_HOST}
    params = {"withAircraftImage": "false", "withLocation": "false"}

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(url, headers=headers, params=params)
    except httpx.HTTPError as exc:
        print(f"request failed: {exc}", file=sys.stderr)
        return 1

    if response.status_code in (204, 404):
        print(f"no flights found for {number} on {day}", file=sys.stderr)
        return 1
    if response.status_code != 200:
        print(f"HTTP {response.status_code}: {response.text[:400]}", file=sys.stderr)
        if response.status_code in (401, 403):
            print(
                "\nA valid RapidAPI key still needs a subscription to this "
                "specific API.\nSubscribe (free Basic tier) at:\n"
                "  https://rapidapi.com/aedbx-aedbx/api/aerodatabox",
                file=sys.stderr,
            )
        return 1

    target = FIXTURES / f"{name}.json"
    target.write_text(
        json.dumps(response.json(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {target.relative_to(Path.cwd())}")

    # Prove the adapter can actually read what we just recorded.
    try:
        adapter = AeroDataBoxProvider(key)
        for flight in await adapter.fetch(number, day):
            print(f"  parsed: {flight.route}  {flight.status.value}")
    except FlightDataError as exc:
        print(f"  WARNING: recorded, but the adapter could not parse it: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
