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

**Rule of thumb: one concept per step, one to three files.** Each step: I explain what the
file will do and why → I write it → I run it and show you the real output → you approve →
I commit. If a step ever looks like it's turning into a pile of files, it gets split.

The order is deliberate: **pure business logic first, infrastructure last.** The compensation
rules are the part you need to verify and the part that must be right. They need no database,
no API key and no server to run — so they come first, and you can read every line of them.

### Phase A — The legal core (pure Python, no infrastructure)

At the end of this phase the entire eligibility decision works and is provable, offline,
with no API key and no database.

| Step | What | Files |
|---|---|---|
| **2** | `pyproject.toml` — minimal `uv` project on Python 3.12 with pytest. Nothing else. | 1 |
| **3** | `domain/distance.py` — the haversine formula. Verified: TLV→LHR = 3,570 km. | 2 |
| **4** | `domain/models.py` — `Money` (Decimal), `FlightStatus`, `FlightFacts` and its two delay properties. | 2 |
| **5** | `data/airports.csv` + `data/airlines.csv` + `domain/reference.py` — code → country, coordinates, carrier nationality. | 3 |
| **6** | `domain/rules/base.py` + `domain/rules/ec261.py` — the `Regulation` protocol and the first real rule. | 3 |
| **7** | `domain/rules/uk261.py` — same shape, British numbers. | 2 |
| **8** | `domain/rules/israel.py` — different threshold, different bands, the 50% reduction. | 2 |
| **9** | `domain/rules/engine.py` — run all three, rank them, produce the explanations. | 2 |

**Step 9 is the milestone.** From that point I can hand you the four worked examples from
`rules.md` running live in a Python shell.

### Phase B — Real flight data

| Step | What | Files |
|---|---|---|
| **10** | `providers/base.py` + `providers/fake.py` + recorded JSON fixtures. | 3 |
| **11** | `providers/aerodatabox.py` — the HTTP client: timeouts, retries, clear errors. | 2 |
| **12** | `providers/mapper.py` — vendor JSON → `FlightFacts`. Timezones, missing actuals, cancellations. | 2 |

### Phase C — Persistence

| Step | What | Files |
|---|---|---|
| **13** | `db/models.py` — the `eligibility_checks` table only. | 2 |
| **14** | Alembic wired up + the initial migration. | 2 |
| **15** | `claims`, `passengers`, `expenses`, `documents` tables + repositories. | 3 |

### Phase D — The HTTP API

| Step | What | Files |
|---|---|---|
| **16** | `config.py` + `main.py` + `/health`. The first infrastructure, and only now. | 3 |
| **17** | `POST /eligibility/check` — validate, fetch, evaluate, persist, return. | 3 |
| **18** | `POST /claims` and document upload. | 3 |
| **19** | `GET /admin/checks` — filtering and pagination. | 2 |

### Phase E — Frontend

| Step | What | Files |
|---|---|---|
| **20** | Next.js + TypeScript + Tailwind scaffold and the design tokens. | ~4 |
| **21** | Typed API client + the strings file. | 2 |
| **22** | The flight-number form: validation, loading state. | 2 |
| **23** | The result screen — explaining a "no" as clearly as it celebrates a "yes". | 2 |
| **24** | The claim wizard: passengers → booking → expenses → receipts → review. | ~5 |
| **25** | Component tests and one end-to-end run. | ~4 |

### Phase F — Handover

| Step | What | Files |
|---|---|---|
| **26** | README setup guide, `Makefile`, `.env.example`, final polish. | 3 |


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
