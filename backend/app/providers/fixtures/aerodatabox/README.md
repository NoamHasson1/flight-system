# AeroDataBox fixtures

⚠️ **These are modelled, not recorded.** They were written by hand from the
published AeroDataBox schema (`FlightContract`, via the OpenAPI spec and the
generated Go/Dart clients), because no API key existed when the adapter was
built.

They are deliberately faithful to the parts that matter and deliberately
incomplete elsewhere — `two_matches.json` omits `aircraft`, `terminal` and
`quality` entirely, which doubles as a test that the parser tolerates absent
optional fields.

## Replacing them with real recordings

Once a RapidAPI key exists:

```bash
export AERODATABOX_API_KEY=...
uv run python scripts/record_fixtures.py BA165 2026-08-14
```

Any difference between these files and the real response shows up immediately
as a failing parser test — which is a far better place to discover schema drift
than production.

## What each one covers

| File | Case |
|---|---|
| `arrived_delayed.json` | The normal path: landed, 4h late, every field populated |
| `cancelled.json` | `status: "Canceled"` (one L), no actual times and never will have any |
| `two_matches.json` | One number flown twice in a day; also sparse optional fields |
