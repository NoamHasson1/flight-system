# Flight Compensation System

Checks whether an air passenger is owed compensation for a delayed or cancelled
flight under **EC261** (EU), **UK261** and the **Israeli Aviation Services Law**
— then collects everything needed to file the claim.

A customer enters a flight number and a date. The system looks up what actually
happened to that flight, applies all three regulations deterministically, and
returns a verdict. If they qualify, a five-step form collects the passengers,
the booking and the receipts.

> ⚠️ This produces an automated estimate, not legal advice.

---

## Run it

Two terminals. Nothing to configure — it works out of the box.

```bash
# 1 · backend  →  http://127.0.0.1:8010
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --port 8010 --reload
```

```bash
# 2 · frontend →  http://localhost:3111
cd frontend
npm install
npm run dev -- --port 3111
```

Open **http://localhost:3111** and enter `BA165` / `2026-08-14`.

> Use `localhost`, not `127.0.0.1`. Next.js treats them as different origins and
> blocks its own dev resources across them, which silently breaks hydration —
> the page renders and nothing is interactive.

API docs: **http://127.0.0.1:8010/docs**

### Flight numbers to try

No API key is needed: the default provider serves scripted scenarios, including
failures you cannot summon from a real API on demand.

| Enter | You get |
|---|---|
| `BA165` / `2026-08-14` | Eligible — £520 under UK261 |
| `BA165` / `2026-08-20` | Eligible under **two** laws at once |
| `LY324` / `2026-08-14` | Eligible — €400 under EC261 |
| `LY325` / `2026-08-14` | Not eligible — same route, opposite direction |
| `LH687` / `2026-08-14` | Needs review — cancelled |
| `FR1234` / `2026-08-14` | Ambiguous — "which flight were you on?" |
| `XX999` | Not found |
| `ERR503` | Provider outage → needs review, never a denial |

---

## Watching a request

`LOG_FLOW=true` (the default outside production) prints one readable block per
check: what the customer sent, the call made to the flight API, what came back,
what it was normalised to, each regulation's answer, the decision, and every
database write.

```
▸ CHECK REQUESTED   BA165 · 2026-08-20
  raw input        'ba 165', '2026-08-20'
  provider         aerodatabox
  → GET            https://aerodatabox.p.rapidapi.com/flights/number/BA165/2026-08-20
  ← response       200 · 1 flight(s)
                   TLV → LHR  BA  LANDED
                     scheduled  dep 2026-08-20 02:20Z  arr 2026-08-20 07:20Z
                     actual     dep 2026-08-20 11:20Z  arr 2026-08-20 16:20Z
  normalised       TLV(IL) → LHR(GB)
                   carrier BA licensed in GB
                   distance 3,589 km (computed, not provided)
                   departure delay 9h 00m   ← Israeli law reads this
                   arrival delay   9h 00m   ← EC261/UK261 read this
  rules
                   ISRAEL  ELIGIBLE     applies=yes   ₪2,450.00
                             …departed 9h 00m late, at or over the 8h 00m threshold…
                   UK261   ELIGIBLE     applies=yes   £520.00
                             …arrived 9h 00m late, at or over the 3h 00m threshold…
                   EC261   NOT_ELIGIBLE applies=no
                             …departs from IL and arrives in GB, and the carrier is GB…
  DECISION         ELIGIBLE  ₪2,450.00 under ISRAEL
                   also payable: UK261 £520.00
  db INSERT        eligibility_checks  id=25fcc91e…  contact_email=n***@example.com …
```

Three things never reach it: the **API key** (it travels in a header precisely
so it stays out of logs), **national identity numbers** (absent, not masked — a
masked secret in a log is still a secret in a log), and **full email addresses**
(masked to `n***@example.com`). The database lines come from a SQLAlchemy
listener rather than from call sites, so nothing can write without appearing —
including code written later by somebody who never read that file.

## Email

Two messages are sent: a **claim confirmation** carrying the reference, and a
**check result** — the latter only when somebody types an address into the
optional field, because a result email nobody asked for is spam.

The default sender is `console`: it writes the full message to the log instead
of sending it, so the system runs with no mail account and cannot email a real
person by accident while you work on it.

To send for real, any SMTP provider works — Postmark, SES, SendGrid, Mailgun,
Resend, your own Postfix — because they all speak SMTP:

```
EMAIL_SENDER=smtp
EMAIL_FROM=Skyclaim <noreply@yourdomain.com>
SMTP_HOST=smtp.postmarkapp.com
SMTP_PORT=587
SMTP_USERNAME=...
SMTP_PASSWORD=...
PUBLIC_BASE_URL=https://yourdomain.com
```

`/health/ready` reports `email: smtp: ok`, and fails readiness if a real sender
is selected with no host — the same reasoning as a missing API key: nothing
errors and nothing alerts while every customer quietly stops getting the email
that tells them their claim exists.

**Sending never blocks or fails a request.** It runs in a background task, and
a dead mail server leaves the claim submitted and the customer looking at their
reference. A confirmation is recorded once sent, so a retry cannot send it
twice — and is deliberately *not* recorded on failure, so a retry can still
pick it up.

## Using real flight data

1. Sign up at [rapidapi.com/aedbx-aedbx/api/aerodatabox](https://rapidapi.com/aedbx-aedbx/api/aerodatabox)
2. **Subscribe to the free Basic tier.** This is the step people miss — a valid
   key on an unsubscribed account returns a 401 that looks exactly like a wrong key
3. Copy your key from the **Code Snippets** panel on any endpoint
4. In `backend/.env` (copy `.env.example` first):

```
FLIGHT_PROVIDER=aerodatabox
AERODATABOX_API_KEY=your-key-here
```

Restart the backend — `.env` is read at startup, not on reload — and check:

```bash
curl http://127.0.0.1:8010/health/ready     # want "aerodatabox: ok"
```

Switch back with `FLIGHT_PROVIDER=fake` any time. Keep using the fake for
frontend work: it is the only way to reproduce an outage or a rate limit.

---

## How it works

```
"BA165" + "2026-08-14"
        │
        ▼
  providers/          ask a flight API what happened          ← the only I/O
        │             (aerodatabox · fake — swappable)
        ▼
  providers/mapper    airport → country + coordinates
        │             airline  → licensing state
        │             the pair → great-circle distance
        ▼
  domain/rules/       EC261 · UK261 · Israel, then rank       ← pure functions
        │
        ▼
  services/           turn every failure into an answer
        │
        ▼
  api/ + db/          serve it, store it
```

**The rules are pure functions.** No network, no database, no clock — the same
flight always produces the same verdict. That is what makes the part that must
be right reviewable without running anything.

### The three principles behind every decision

**1. A wrong "no" is worse than a wrong "yes".** A wrong yes gets caught by a
human downstream. A wrong no costs the passenger money and is never discovered,
because they close the tab. Hence a three-way verdict, `None` instead of `0`
delays, unknown airports returning `None`, and every provider failure becoming
`NEEDS_REVIEW`.

**2. Refuse bad input; never launder it.** Floats rejected for money, naive
datetimes rejected outright, malformed CSV rows rejected with file and line.
Each could be "handled gracefully" into a plausible wrong number.

**3. Pure logic first, infrastructure last.** The whole legal core was finished
and tested before FastAPI, a database or an API key existed.

### The rules, in one table

| | EC261 | UK261 | Israel |
|---|---|---|---|
| Clock | arrival | arrival | **departure** |
| Threshold | 3 h | 3 h | **8 h** |
| Bands | 1,500 / 3,500 km | 1,500 / 3,500 km | **2,000 / 4,500 km** |
| Amounts | €250 / €400 / €600 | £220 / £350 / £520 | ₪1,530 / ₪2,450 / ₪3,670 |
| Carrier test | yes, decisive | yes, wider | **none** |
| 50% reduction | no | no | **yes, on the other clock** |

[`rules.md`](rules.md) explains all of it in plain English, with worked examples.
Every figure in it maps to a named constant in one file.

---

## Tests

```bash
cd backend  && uv run pytest        # 551
cd frontend && npm test             #  21
cd frontend && npm run e2e          #   4  (needs both servers running)
```

**576 tests.** The ones worth knowing about:

- `tests/acceptance/test_real_flights.py` — 27 real airlines on real routes,
  every expectation derived by hand from `rules.md` **before** the code was run.
  A test written by recording what the system said proves only that it agrees
  with itself.
- `tests/unit/test_aerodatabox.py` — includes a genuinely **recorded** response,
  so a schema change at AeroDataBox fails here rather than in production.
- `e2e/journey.spec.ts` — three of its four cases are about answers that must
  never render as a denial.

---

## Layout

```
backend/
  app/domain/        distance · money · reference data · the three rules
  app/providers/     the flight-data port, its adapters, and the mapper
  app/services/      the eligibility use case
  app/db/            models, migrations, repositories
  app/api/           FastAPI routes
  app/data/          4,133 airports · 113 airlines, committed not fetched
frontend/
  src/app/           landing · /check/[id] · /claim/[id]
  src/components/    the check form and the claim wizard
  src/lib/           typed client (generated from the API), all copy
```

`npm run types` regenerates the client types from the running backend, so the
frontend cannot drift from the API.

---

## Known gaps

Named deliberately rather than left to be discovered.

| | |
|---|---|
| **`national_id` is not encrypted** | Sensitive under GDPR and Israeli law. Must be encrypted at rest with a retention policy **before a real customer uses this** |
| **Arrival time is touchdown** | The law counts from the doors opening (*Germanwings* C-452/13), 5–15 minutes later. EC261/UK261 send anything within 15 minutes of the threshold to review rather than deny it |
| **No multi-leg support** | A missed connection is compensated on the *final* destination and *total* distance. The biggest coverage gap |
| **Denied boarding** | Covered by all three laws, undetectable from any API. Needs a self-declared path |
| **No claim letter** | A PDF citing the exact article is arguably the real product |
| **Admin is API-only** | Guarded by a shared key, read-only. No UI yet |
| **SQLite** | Fine for one machine. Alembic makes Postgres a connection-string change |

---

## Documents

| File | |
|---|---|
| [`plan.md`](plan.md) | Architecture, the 26 build steps, testing strategy, roadmap |
| [`rules.md`](rules.md) | The compensation rules in plain English, with worked examples |
| `backend/.env.example` | Every setting, with the reasoning |

The git history is the other documentation: 32 commits, each one step, each
message explaining why rather than what.
