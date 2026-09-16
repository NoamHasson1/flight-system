# Flight Compensation System

Checks whether an air passenger is owed compensation for a delayed or cancelled flight
under **EC261** (EU), **UK261** (United Kingdom) and the **Israeli Aviation Services Law**
(the Tibi Law) — then collects everything needed to file the claim.

A customer enters a flight number and a date. The system looks up what actually happened to
that flight, evaluates all three regulations, and returns a verdict with its reasoning.

## Documents

| File | What's in it |
|---|---|
| [`plan.md`](plan.md) | The full implementation plan — architecture, the 14 build steps, testing strategy, roadmap |
| [`rules.md`](rules.md) | The compensation rules in plain English, with worked examples |

## Layout

```
backend/    Python 3.12 · FastAPI · SQLAlchemy · SQLite
frontend/   Next.js (App Router) · TypeScript · Tailwind
```

## Status

🚧 Under construction — see the step list in [`plan.md`](plan.md#4-the-steps).
Setup instructions land in Step 14.

---

> ⚠️ This system provides an automated estimate, not legal advice.
