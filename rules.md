# Flight Compensation Rules — In Plain English

This document explains, in everyday language, how the system decides whether a passenger
gets money for a disrupted flight. It is written so that a non-programmer can read it and
understand exactly what the system does and why.

Every rule described here has a matching, testable function in the code
(`backend/app/domain/rules/`). If this document and the code ever disagree, that is a bug.

---

## 1. The one-paragraph summary

Three different laws can give a passenger money for a delayed or cancelled flight: the
**European** one (EC261), the **British** one (UK261), and the **Israeli** one (the Aviation
Services Law, often called the *Tibi Law*). A single flight can qualify under more than one
of them. Our system checks all three, tells the passenger every law they qualify under, and
highlights the one that pays the most.

---

## 2. The three questions we ask about every flight

For each of the three laws, we ask the same three questions in the same order:

1. **Does this law apply to this flight at all?** (a question about geography and airline)
2. **Was the disruption bad enough?** (a question about hours)
3. **How much money is owed?** (a question about distance)

If the answer to question 1 or 2 is "no", that law pays nothing. We move on to the next law.

---

## 3. How we measure a delay

This is the single most important detail, and it is the one people get wrong most often.

> **We measure the delay at ARRIVAL, not at departure.**

If your plane pushed back 5 hours late but the pilot made up time and you landed only
2 hours late, European and British law say you get **nothing**. What counts is how late you
walked off the plane at your final destination compared to when you were scheduled to.

```
arrival delay  =  actual arrival time  −  scheduled arrival time
```

The Israeli law is the exception and works differently — see section 6.

**Cancelled flights** are treated as a special case. If the airline cancelled your flight and
told you less than 14 days before departure, you are treated as eligible under EC261/UK261
without needing to prove an arrival delay.

---

## 4. How we measure distance

Distance decides how much money you get. We use the **great-circle distance** — the shortest
path over the curve of the Earth — between the **first departure airport** and the **final
destination airport**. Not the distance the plane actually flew, and not the road distance.

We compute it with the haversine formula from the published latitude/longitude of each
airport. Example: Tel Aviv (TLV) to London Heathrow (LHR) is about **3,570 km**.

---

## 5. EC261 — the European regulation

### Does it apply?

Yes, if **either** of these is true:

- The flight **departs from an airport in the EU/EEA** — the airline can be from anywhere in
  the world. (El Al flying Paris → Tel Aviv counts.)
- The flight **arrives at an airport in the EU/EEA** *and* is operated by an
  **EU-licensed airline**. (Lufthansa flying Tel Aviv → Frankfurt counts. El Al flying
  Tel Aviv → Frankfurt does **not**, because El Al is not an EU carrier.)

### Was it bad enough?

| Distance | Delay needed |
|---|---|
| Up to 1,500 km | 3 hours or more |
| 1,500 – 3,500 km | 3 hours or more |
| Over 3,500 km | 3 hours or more |

> **Note on the "4 hour" rule you may have read about.** For long flights over 3,500 km that
> cross outside the EU, the compensation can be *halved* if the airline gets you there under
> 4 hours late. The passenger is still eligible at 3 hours — they just receive 50%. We apply
> this reduction rather than denying the claim.

### How much?

| Distance | Compensation |
|---|---|
| Up to 1,500 km | **€250** |
| 1,500 – 3,500 km | **€400** |
| Over 3,500 km | **€600** |

---

## 6. Israeli Aviation Services Law (Tibi Law)

### Does it apply?

Yes, if the flight **departs from Israel or arrives in Israel**. The airline's nationality
does not matter.

### Was it bad enough?

The Israeli threshold is much higher than the European one, and it is measured from the
**scheduled departure time**:

> The flight must be delayed by **8 hours or more** from its original scheduled departure.

### How much?

| Distance | Compensation |
|---|---|
| Up to 2,000 km | **₪1,530** |
| 2,000 – 4,500 km | **₪2,450** |
| Over 4,500 km | **₪3,670** |

Notice these distance bands are **different** from the European ones (2,000/4,500 km rather
than 1,500/3,500 km). This is a common source of mistakes.

### The 50% reduction

The amount is **cut in half** if the airline still got you to your destination reasonably
close to on time:

| Distance | Amount is halved if arrival delay is under |
|---|---|
| Up to 2,000 km | 4 hours |
| 2,000 – 4,500 km | 5 hours |
| Over 4,500 km | 6 hours |

> These shekel amounts are **linked to the Israeli consumer price index and updated each
> year**. In the code they live in one clearly-marked constants file so they can be updated
> annually without touching any logic.

---

## 7. UK261 — the British regulation

After Brexit, the UK copied EC261 into its own law, changed the currency, and kept almost
everything else identical.

### Does it apply?

Yes, if **either** of these is true:

- The flight **departs from an airport in the UK** — any airline.
- The flight **arrives at an airport in the UK** *and* is operated by a **UK or EU-licensed
  airline**.

### Was it bad enough?

Same as EC261: **3 hours or more** of arrival delay.

### How much?

| Distance | Compensation |
|---|---|
| Up to 1,500 km | **£220** |
| 1,500 – 3,500 km | **£350** |
| Over 3,500 km | **£520** |

---

## 8. When the airline does NOT have to pay: "extraordinary circumstances"

All three laws excuse the airline when the disruption was genuinely outside its control:

- Severe weather
- Air traffic control strikes, or strikes by people who don't work for the airline
- Security threats, political instability, closed airspace
- A bird strike or similar unforeseeable safety issue

These do **not** count as extraordinary — the airline still pays:

- Technical or mechanical faults with the aircraft
- A strike by the airline's own staff
- Crew scheduling problems
- Knock-on delays from an earlier flight of the same aircraft

### How our system handles this

**No flight data API tells us why a flight was late.** So the system cannot decide this
automatically, and it does not pretend to. Instead:

- The eligibility result always carries a clearly-worded caveat saying the answer assumes
  the cause was within the airline's control.
- When the passenger moves on to submit a claim, we ask them what reason the airline gave.

This is deliberate honesty. Telling someone "you are definitely owed €600" when a
thunderstorm closed the airport would be worse than useless.

---

## 9. Putting it together: worked examples

### Example A — Tel Aviv → London, 4 hours late

- Distance TLV→LHR: **3,570 km**
- Arrival delay: **4h 00m**

| Law | Applies? | Bad enough? | Result |
|---|---|---|---|
| EC261 | ❌ No — neither end is in the EU | — | Nothing |
| UK261 | ✅ Yes — arrives in the UK, and it's a British Airways flight (UK carrier) | ✅ 4h ≥ 3h | **£520** |
| Israel | ✅ Yes — departs Israel | ❌ 4h is under the 8h threshold | Nothing |

**Verdict: eligible — £520 under UK261.**

### Example B — Tel Aviv → London, 9 hours late

Same flight, worse delay. Departure was delayed 9 hours; arrival delay is also 9 hours.

| Law | Applies? | Bad enough? | Result |
|---|---|---|---|
| EC261 | ❌ No | — | Nothing |
| UK261 | ✅ Yes | ✅ 9h ≥ 3h | **£520** |
| Israel | ✅ Yes | ✅ 9h ≥ 8h | **₪2,450** (3,570 km falls in the 2,000–4,500 band; arrival delay 9h is over 5h, so no 50% cut) |

**Verdict: eligible under two laws. We show both and highlight ₪2,450 as the larger amount.**

### Example C — Paris → Tel Aviv on El Al, 3.5 hours late

- Distance CDG→TLV: **3,290 km**
- Arrival delay: **3h 30m**

| Law | Applies? | Bad enough? | Result |
|---|---|---|---|
| EC261 | ✅ Yes — **departs** from the EU, so the airline's nationality is irrelevant | ✅ 3.5h ≥ 3h | **€400** |
| UK261 | ❌ No | — | Nothing |
| Israel | ✅ Yes — arrives in Israel | ❌ Under 8h | Nothing |

**Verdict: eligible — €400 under EC261.**

### Example D — Tel Aviv → New York, 2 hours late

| Law | Applies? | Bad enough? | Result |
|---|---|---|---|
| EC261 | ❌ No | — | Nothing |
| UK261 | ❌ No | — | Nothing |
| Israel | ✅ Yes | ❌ Way under 8h | Nothing |

**Verdict: not eligible.** The system explains that the flight was covered by Israeli law but
the 2-hour delay did not reach the 8-hour threshold — so the passenger understands *why*.

---

## 10. What the system does NOT decide

Being transparent about the boundaries matters as much as the rules themselves.

- **Why** the flight was late (see section 8).
- **Denied boarding / overbooking.** Covered by all three laws, but no API can detect it.
  Planned as a self-declared path in a later version.
- **Downgrades and missed connections.** Out of scope for version 1.
- **The 2-year to 6-year claim time limits**, which vary by country and by where you sue.
- **Reimbursement of your ticket**, which is a separate right from compensation.
- **Consequential expenses** (hotels, meals, taxis). These are a real right under all three
  laws, but they are reimbursed at cost against receipts rather than as a fixed sum, so the
  system **collects** them during claim intake instead of calculating them.

---

## 11. Where these numbers live in the code

Every figure in this document is defined once, as a named constant, in:

```
backend/app/domain/rules/ec261.py    → €250 / €400 / €600, 1500 km, 3500 km, 3 h
backend/app/domain/rules/uk261.py    → £220 / £350 / £520, 1500 km, 3500 km, 3 h
backend/app/domain/rules/israel.py   → ₪1,530 / ₪2,450 / ₪3,670, 2000 km, 4500 km, 8 h
```

No magic numbers are scattered through the logic. When the Israeli amounts are re-indexed
next year, exactly one file changes.

---

## 12. Sources

- EC261: [Regulation (EC) No 261/2004 explained](https://onemileatatime.com/guides/ec261-europe-flight-compensation/)
- UK261: [UK261 compensation rules and amounts](https://onemileatatime.com/guides/uk261-united-kingdom-flight-compensation/)
- Israel: [Israeli Aviation Services Law](https://www.virginatlantic.com/policies/israeli-aviation-services-law),
  [passenger rights guide](https://eshimony-law.com/aviation-law/flight-to-or-from-israel-delayed-or-cancelled-your-compensation-rights-guide/)

> ⚠️ This system provides an automated estimate, not legal advice.
