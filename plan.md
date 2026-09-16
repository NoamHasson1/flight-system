# Flight Compensation System — Implementation Plan

> **How this document is used.** This is the contract for the build. We work through the
> steps in order. Before each step I explain what I'm about to do and show you an example of
> the output; I do not start the next step until you approve the current one. Each approved
> step becomes one git commit, so `git log` reads as the story of the build.

---

## 1. What we are building

A customer types a **flight number** and a **flight date**. The system looks up what actually
happened to that flight, runs it through three compensation regulations, and answers one
question: **are you owed money, and how much?**

If the answer is yes, the customer continues into a claim form where they provide passenger
details, their booking, and any out-of-pocket expenses with receipts. Every check — eligible
or not — is recorded in a database.

### The two user journeys

```
JOURNEY 1 — "Am I owed anything?"          JOURNEY 2 — "Then let's claim it"
┌──────────────────────────┐               ┌──────────────────────────┐
│ Flight number: LY315     │               │ Passengers               │
│ Date: 2026-08-14         │               │  • Full name + ID        │
└────────────┬─────────────┘               │ Booking reference        │
             ▼                             │ Expenses + receipts      │
    ┌────────────────┐                     └────────────┬─────────────┘
    │ Flight API     │                                  ▼
    └────────┬───────┘                          ┌───────────────┐
             ▼                                  │ Claim stored  │
    ┌────────────────┐                          └───────────────┘
    │ Rules engine   │  EC261 / UK261 / Israel
    └────────┬───────┘
             ▼
    ┌────────────────────────────────┐
    │ ✅ Eligible — £520 under UK261 │  ──► saved to database
    │ ❌ Not eligible — and why      │
    └────────────────────────────────┘
```

---

## 2. Decisions already locked in

| Decision | Choice | Why |
|---|---|---|
| Backend | Python 3.12 + FastAPI | Type hints end-to-end, automatic OpenAPI docs, async HTTP |
| Frontend | Next.js (App Router) + TypeScript + Tailwind | Industry standard, server components, great DX |
| Flight data | **AeroDataBox** via RapidAPI | Cheapest provider that gives *actual arrival times* and *historical* flights — both mandatory here |
| Database | **SQLite** via SQLAlchemy 2.0 + Alembic | Zero setup, one inspectable file; Alembic means Postgres later is a connection-string change |
| Language | English only | All copy routed through one strings file so Hebrew/RTL can be added without touching components |
| Scope v1 | Delay **and** cancellation | Both are auto-detectable from the API; denied boarding needs self-declaration and is deferred |
| Package manager | `uv` | Fast, lockfile-based, manages the Python version itself (system Python here is 3.9) |
| Repo | Monorepo, one git repo | `backend/` and `frontend/` side by side; one history |

---

## 3. Architecture

The guiding principle is **the rules are pure functions**. Everything that touches the
network, the disk, or the clock is pushed to the edges. That is what makes the compensation
logic — the part that must be right — trivially testable with no mocks.

```
        HTTP (FastAPI routes)          ← thin: validate, call service, serialise
                  │
        Services (orchestration)       ← fetch flight, evaluate, persist
             │          │
   ┌─────────┘          └──────────┐
   ▼                               ▼
Providers                       Domain                     Database
(AeroDataBox,                   (rules, distance,          (SQLAlchemy
 Fake/fixtures)                  money) — PURE              models, repos)
   │                                                            │
   ▼                                                            ▼
Flight API                                                  flight_system.db
```

### Backend directory layout

```
backend/
├── pyproject.toml              # deps, tooling config (ruff, mypy, pytest)
├── app/
│   ├── main.py                 # FastAPI app factory
│   ├── config.py               # pydantic-settings, reads .env
│   ├── api/
│   │   ├── deps.py             # DI: get_db, get_flight_provider
│   │   └── routes/
│   │       ├── eligibility.py  # POST /eligibility/check
│   │       ├── claims.py       # POST /claims, uploads
│   │       └── admin.py        # GET /admin/checks
│   ├── domain/                 # ← PURE. No imports of db/http/os.
│   │   ├── models.py           # FlightFacts, Money, RegulationOutcome, EligibilityResult
│   │   ├── distance.py         # haversine
│   │   ├── reference.py        # airport → country/coords, airline → country
│   │   └── rules/
│   │       ├── base.py         # the Regulation protocol
│   │       ├── ec261.py
│   │       ├── uk261.py
│   │       ├── israel.py
│   │       └── engine.py       # run all three, rank, explain
│   ├── providers/
│   │   ├── base.py             # FlightDataProvider protocol
│   │   ├── aerodatabox.py      # real client
│   │   └── fake.py             # fixture-backed, used by tests and offline dev
│   ├── data/
│   │   ├── airports.csv        # IATA → lat, lon, country
│   │   └── airlines.csv        # IATA → name, country of licence
│   ├── db/
│   │   ├── session.py          # engine + session factory
│   │   ├── models.py           # ORM tables
│   │   ├── repositories.py     # the only place that writes SQL
│   │   └── migrations/         # alembic
│   ├── schemas/                # pydantic request/response DTOs
│   ├── services/
│   │   ├── eligibility.py
│   │   └── claims.py
│   └── storage/                # receipt files on local disk (S3-swappable)
└── tests/
    ├── unit/                   # domain — no I/O, milliseconds
    ├── integration/            # db + provider parsing
    ├── api/                    # FastAPI TestClient
    └── fixtures/               # recorded AeroDataBox JSON
```

### The central data structure

Everything the rules need is normalised into one flat, boring object. The rules never see
an API response.

```python
@dataclass(frozen=True)
class FlightFacts:
    flight_number: str
    flight_date: date
    airline_iata: str
    airline_country: str          # country that licensed the carrier
    origin_iata: str
    origin_country: str
    destination_iata: str
    destination_country: str
    distance_km: float            # great-circle
    scheduled_departure: datetime  # timezone-aware, UTC
    actual_departure: datetime | None
    scheduled_arrival: datetime
    actual_arrival: datetime | None
    status: FlightStatus          # ARRIVED | CANCELLED | ...

    @property
    def arrival_delay_hours(self) -> float | None: ...
    @property
    def departure_delay_hours(self) -> float | None: ...
```

### What a result looks like

The API never returns a bare yes/no. It returns the reasoning, because the frontend needs to
explain the verdict and because an unexplained "no" destroys trust.

```json
{
  "check_id": "c7f3...",
  "eligible": true,
  "best_award": { "regulation": "UK261", "amount": 520.00, "currency": "GBP" },
  "flight": {
    "flight_number": "BA165", "route": "TLV → LHR",
    "distance_km": 3570, "arrival_delay_hours": 4.0, "status": "ARRIVED"
  },
  "outcomes": [
    { "regulation": "EC261",  "applies": false, "eligible": false,
      "reason": "Neither the departure nor the arrival airport is in the EU/EEA." },
    { "regulation": "UK261",  "applies": true,  "eligible": true,
      "amount": 520.00, "currency": "GBP",
      "reason": "Arrives in the UK on a UK carrier; arrival delay of 4h 0m exceeds the 3-hour threshold; distance 3,570 km is over 3,500 km." },
    { "regulation": "ISRAEL", "applies": true,  "eligible": false,
      "reason": "Covered (departs Israel), but the 4h 0m delay is below the 8-hour threshold." }
  ],
  "caveat": "This estimate assumes the disruption was within the airline's control."
}
```

### Database schema

```
eligibility_checks                 claims                     passengers
──────────────────                 ──────                     ──────────
id            (uuid, pk)           id          (uuid, pk)     id        (uuid, pk)
created_at                         check_id    (fk) ──────┐   claim_id  (fk) ──┐
flight_number                      status                 │   full_name        │
flight_date                        booking_reference      │   national_id      │
contact_name                       contact_email          │                    │
contact_email                      created_at             │                    │
eligible      (bool)               updated_at             │   expenses          │
regulation                                                │   ────────          │
amount / currency                                         │   id       (uuid,pk)│
flight_snapshot  (json)  ← exactly what the API said      │   claim_id (fk) ────┘
result_detail    (json)  ← full outcome list              │   category
                                                          │   description
documents                                                 │   amount / currency
─────────                                                 │
id, claim_id (fk), kind (booking|receipt), filename, stored_path, content_type, size
```

Two design notes worth calling out:

1. **`flight_snapshot` stores the raw normalised facts.** If we later fix a bug in a rule, we
   can re-run every historical check against the new logic without paying the API again.
2. **Every check is saved, eligible or not.** You asked for this, and it is also the most
   commercially valuable table in the system — it is a list of people with flight problems.

---

## 4. The steps

Each step: I explain it → I show you an example → you approve → I commit.

### Step 1 — Repository scaffold and planning documents ← *you are here*
`plan.md`, `rules.md`, `README.md`, `.gitignore`, git repo on `main`.
**Example shown:** these two documents.
**Commit:** `chore: initialise repo with plan and rules documentation`

### Step 2 — Backend skeleton
`uv` project pinned to Python 3.12, FastAPI app factory, `config.py` with pydantic-settings,
`/health` endpoint, ruff + mypy + pytest configured, one passing test.
**Example shown:** the server running, `curl /health`, `/docs` page, `pytest` output.
**Commit:** `feat(backend): scaffold FastAPI application with tooling`

### Step 3 — Domain foundations
`FlightFacts`, `Money`, `EligibilityResult`; haversine distance; the bundled `airports.csv`
and `airlines.csv` plus the lookup layer.
**Example shown:** `distance("TLV","LHR") → 3570 km` verified against a published figure.
**Commit:** `feat(domain): flight facts, money types and great-circle distance`

### Step 4 — The rules engine ⭐ *the heart of the system*
`ec261.py`, `uk261.py`, `israel.py`, each a small pure module with the constants from
`rules.md` at the top; `engine.py` runs all three and ranks them.
**Example shown:** the four worked examples from `rules.md`, evaluated live.
**Commit:** `feat(domain): EC261, UK261 and Israeli compensation rules`

### Step 5 — Flight data provider
`FlightDataProvider` protocol; `FakeFlightProvider` reading JSON fixtures; `AeroDataBoxProvider`
with httpx, retries, timeouts and clear "flight not found" errors; the mapper that turns an
API response into `FlightFacts`.
**Example shown:** the same flight resolved through both the fake and (if the key is ready)
the real provider, producing an identical `FlightFacts`.
**Commit:** `feat(providers): AeroDataBox client with fixture-backed fake`

### Step 6 — Database layer
SQLAlchemy 2.0 models, Alembic initial migration, repository functions.
**Example shown:** `alembic upgrade head`, then the created tables listed from the sqlite CLI.
**Commit:** `feat(db): SQLAlchemy models, migrations and repositories`

### Step 7 — Eligibility endpoint
`POST /api/v1/eligibility/check` — validate, fetch, evaluate, persist, return.
**Example shown:** a real `curl` request and the full JSON response, then the saved row.
**Commit:** `feat(api): eligibility check endpoint`

### Step 8 — Claim intake
`POST /api/v1/claims` (passengers, booking, expenses), `POST /api/v1/claims/{id}/documents`
for file uploads with type/size validation, `GET /api/v1/claims/{id}`.
**Example shown:** submitting a claim with two passengers and a receipt upload.
**Commit:** `feat(api): claim submission with passengers, expenses and documents`

### Step 9 — Admin read API
`GET /api/v1/admin/checks` with filtering and pagination, so the data is easy to look at.
**Example shown:** a filtered listing.
**Commit:** `feat(api): admin endpoints for browsing checks and claims`

### Step 10 — Frontend scaffold and design system
Next.js + TypeScript + Tailwind, design tokens, typed API client, the strings file.
Guided by the **apple-design** skill: restraint, real materials, honest motion.
**Example shown:** the landing page and the token palette.
**Commit:** `feat(frontend): Next.js scaffold with design system`

### Step 11 — The check flow
The flight-number form with real validation, the loading state, and the result screen —
which must explain a "no" as clearly as it celebrates a "yes".
**Example shown:** screenshots of eligible and not-eligible results.
**Commit:** `feat(frontend): flight eligibility check flow`

### Step 12 — The claim flow
Multi-step form: passengers → booking → expenses → receipts → review → submit. Progress is
preserved if the user refreshes.
**Example shown:** a full walkthrough.
**Commit:** `feat(frontend): multi-step claim submission flow`

### Step 13 — Frontend tests and end-to-end check
Vitest + Testing Library for components; one Playwright run through the whole journey.
**Commit:** `test(frontend): component and end-to-end coverage`

### Step 14 — Documentation and handover
README with setup instructions, a `Makefile`, `.env.example`, final polish.
**Commit:** `docs: setup, architecture and operations guide`

---

## 5. Testing strategy — and *why* each kind of test exists

You asked me to explain the reasoning, not just write tests. Tests are not free; each type
below earns its place by catching a specific class of bug.

### Unit tests on the rules — *the ones that actually matter*
The compensation logic is where a bug costs real money and real trust. These tests are pure
functions in, dataclasses out: no database, no network, no mocks, milliseconds to run. That
purity is the whole reason the architecture pushes I/O to the edges.

The cases are deliberately chosen around **boundaries**, because that is where rules break:

| Case | Why it's tested |
|---|---|
| Arrival delay 2h59m vs 3h01m | The single most important threshold in EC261/UK261 |
| Distance 1,499 km vs 1,501 km | Band boundary — an off-by-one pays €150 too little |
| Distance 3,499 km vs 3,501 km | The other band boundary |
| Israeli delay 7h59m vs 8h01m | Israel's threshold is different from Europe's |
| Israeli distance 1,999 / 2,001 / 4,501 km | Israel's bands are *different numbers* — easy to copy-paste wrong |
| Israeli 50% reduction at each band | Complex conditional rule, high bug risk |
| El Al flying Paris → Tel Aviv | Proves departure-from-EU works for a non-EU carrier |
| El Al flying Tel Aviv → Frankfurt | Proves arrival-into-EU correctly *fails* for a non-EU carrier |
| Big departure delay, small arrival delay | Guards the "measure at arrival" rule — the classic mistake |
| Cancelled flight | Different code path entirely |
| Flight qualifying under two laws | Proves the engine ranks and returns both |
| Flight with no actual arrival yet | Must not crash on `None`; must say "too early to tell" |

### Property-based tests (Hypothesis) on distance and money
Over thousands of generated coordinate pairs we assert invariants that must *always* hold:
distance is symmetric, distance to self is zero, the result never exceeds half the Earth's
circumference. Hand-written examples can't cover that space. Money arithmetic uses `Decimal`
and is checked for rounding correctness — floats have no place in a payout amount.

### Integration tests on the provider
These do **not** call the real API — that would be slow, flaky, and cost money on every CI
run. Instead we save real AeroDataBox responses once as fixtures and test the *mapper*: does
this JSON become the right `FlightFacts`? They also cover the ugly realities — missing actual
arrival times, cancelled flights, timezone offsets, unknown airport codes.

### API tests with FastAPI's TestClient
These verify the wiring, not the logic: a bad date returns 422 with a useful message, an
unknown flight returns 404 rather than a stack trace, a successful check writes exactly one
database row. The flight provider is swapped for the fake via dependency injection, so these
run offline in under a second.

### Frontend component tests
Only where there is real logic or a real risk: form validation, the result screen rendering
both verdicts correctly, the multi-step form preserving state. We do not test that Tailwind
applies a class — that tests the framework, not our code.

### One end-to-end test
A single Playwright run through the entire journey: type a flight number → see a verdict →
fill a claim → submit. It is slow, so there is exactly one. It exists to catch the integration
failures that unit tests structurally cannot see.

---

## 6. Ideas to make the system better

You asked for research and suggestions. These are **not** in the 14 steps above — they are
the roadmap after v1, ordered by my honest view of value-for-effort.

### High value, low effort
1. **Airline reason capture.** Ask the customer what the airline told them, and match it
   against a curated list of excuses that do *not* count as extraordinary (technical fault,
   own-staff strike). This turns the caveat in section 8 of `rules.md` into a real signal.
2. **Multi-leg and connecting flights.** Today the system checks one flight number. A missed
   connection on a single booking is compensated on the *final* destination and the *total*
   distance — and it is extremely common. This is the biggest coverage gap in v1.
3. **Claim reference number + status page.** A lookup URL so customers can check progress
   without emailing you. Cuts support load immediately.
4. **Automatic claim letter generation.** Produce a PDF demand letter addressed to the airline,
   citing the exact regulation and article. This is the actual product value — most people
   stall at "now what do I write?".
5. **Caching flight lookups.** A completed flight's data never changes. Cache by
   `(flight_number, date)` forever. On a $7.50 plan with 5,000 calls, repeat lookups are pure
   waste, and the same flight gets checked by many passengers.
6. **Time-limit warning.** Tell the customer how long they have left to claim (2–6 years
   depending on jurisdiction). Creates urgency and prevents worthless claims.

### High value, medium effort
7. **Admin dashboard.** A real UI over the checks table: conversion funnel, which routes and
   airlines generate claims, total value in the pipeline.
8. **Email notifications.** Confirmation on submission, updates on status change.
9. **Duplicate-passenger detection.** Multiple passengers on one flight often check
   separately. Group them into one claim — cheaper for you, stronger against the airline.
10. **Rule versioning.** Store *which version* of the rules produced each verdict. The EU is
    actively revising EC261 (a 2026 agreement is pending adoption), and the Israeli amounts
    are re-indexed annually. Without versioning, old verdicts become unexplainable.
11. **"Watch my flight."** Let a user register an upcoming flight; check it automatically
    after landing and email them if they're owed money. Converts a one-off tool into a
    recurring relationship.

### Strategic
12. **Bulk/corporate intake.** Travel agencies and companies have many affected employees.
13. **Airline response tracking.** Log what each airline pays and how fast; that dataset
    becomes genuine negotiating leverage.
14. **Hebrew + RTL.** Deferred from v1 but essential for the Israeli market — the reason all
    copy goes through a strings file from day one.

### Operational hardening
15. **Rate limiting** on the check endpoint — it costs you money per call.
16. **Structured JSON logging** with a request ID threaded through every log line.
17. **PII handling.** ID numbers and receipts are sensitive personal data. Encrypt at rest,
    define a retention policy, and add a deletion endpoint. Worth doing before real customers.
18. **CI on every push** — ruff, mypy, pytest, and the frontend build.

---

## 7. Ground rules for the build

- **No cleverness.** Boring, readable code. If a rule needs a comment to explain *what* it
  does, it is written wrong.
- **Constants once.** Every amount and threshold appears in exactly one place and matches
  `rules.md`.
- **Type hints everywhere**, checked by mypy in strict mode.
- **No floats for money.** `Decimal`, always.
- **Every timestamp is timezone-aware UTC** at the boundary. Aviation data is a minefield of
  local times; we normalise once, on the way in.
- **The domain layer imports nothing from `db/`, `api/` or `providers/`.** Enforced by review,
  and visible at a glance from the import list.
