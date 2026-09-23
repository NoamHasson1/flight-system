"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { strings } from "@/lib/strings";

import s from "./hero.module.css";

/**
 * The compensation calculator.
 *
 * WHY THE BANDS ARE PASSED IN
 * ---------------------------
 * They come from /api/v1/regulations, which reads them out of the rules
 * engine. A calculator with its own copy of 1,530 is a calculator that
 * eventually quotes a figure the check will not honour -- and of everything
 * on this site, the number somebody does arithmetic with is the one that has
 * to be right.
 *
 * WHY IT IS AN ESTIMATE AND SAYS SO
 * ---------------------------------
 * It knows the distance and what happened. It does NOT know how long the
 * delay was, what the airline will claim as the cause, or when they gave
 * notice -- the three things that actually decide a claim. Presenting a
 * confident figure would be a promise this page cannot keep, so it presents a
 * range-shaped answer and points at the real check.
 */

type Band = { up_to_km: number | null; amount: string; currency: string };
type Regulation = { key: string; bands: Band[] };

const SYMBOL: Record<string, string> = { ILS: "₪", EUR: "€", GBP: "£" };
const LAW_NAME: Record<string, string> = {
  ISRAEL: "החוק הישראלי",
  EC261: "התקנה האירופית",
  UK261: "החוק הבריטי",
};

export function Calculator({ regulations }: { regulations: Regulation[] }) {
  const c = strings.calculator;
  const [km, setKm] = useState<number | null>(null);
  const [otherKm, setOtherKm] = useState("");
  const [event, setEvent] = useState<string | null>(null);
  const [passengers, setPassengers] = useState(1);

  const distance = km === 0 ? Number(otherKm) || 0 : (km ?? 0);

  const results = useMemo(() => {
    if (!distance || !event) return [];
    return regulations
      .map((regulation) => {
        const band = regulation.bands.find(
          (b) => b.up_to_km === null || distance <= b.up_to_km,
        );
        if (!band) return null;
        const each = Number(band.amount.replace(/,/g, ""));
        return {
          key: regulation.key,
          symbol: SYMBOL[band.currency] ?? "",
          each,
          total: each * passengers,
        };
      })
      .filter((x): x is NonNullable<typeof x> => x !== null);
  }, [distance, event, passengers, regulations]);

  return (
    <section className="px-5 pb-20 sm:px-8">
      <div className="mx-auto grid max-w-5xl gap-6 lg:grid-cols-[1.1fr_1fr]">
        {/* --- the questions -------------------------------------------- */}
        <div className={`${s.calcCard}`}>
          <Field label={c.destination} hint={c.destinationHint}>
            <div className="flex flex-wrap gap-2">
              {c.destinations.map((d) => (
                <button
                  key={d.label}
                  type="button"
                  onClick={() => setKm(d.km)}
                  className={`${s.choice} ${km === d.km ? s.choiceOn : ""}`}
                >
                  {d.label}
                </button>
              ))}
            </div>
            {km === 0 ? (
              <input
                type="number"
                inputMode="numeric"
                value={otherKm}
                onChange={(e) => setOtherKm(e.target.value)}
                placeholder={c.otherKm}
                aria-label={c.otherKm}
                className={`${s.field} mt-3 w-full px-4 py-3`}
              />
            ) : null}
          </Field>

          <Field label={c.whatHappened}>
            <div className="flex flex-wrap gap-2">
              {c.events.map((e) => (
                <button
                  key={e.key}
                  type="button"
                  onClick={() => setEvent(e.key)}
                  className={`${s.choice} ${event === e.key ? s.choiceOn : ""}`}
                >
                  {e.label}
                </button>
              ))}
            </div>
          </Field>

          <Field label={c.passengers} hint={c.passengersHint}>
            <div className="flex items-center gap-3">
              <Stepper
                onClick={() => setPassengers((n) => Math.max(1, n - 1))}
                label="−"
                disabled={passengers <= 1}
              />
              <span
                className={`${s.code} w-12 text-center text-title`}
                style={{ color: "var(--text-strong)" }}
                aria-live="polite"
              >
                {passengers}
              </span>
              <Stepper
                onClick={() => setPassengers((n) => Math.min(9, n + 1))}
                label="+"
                disabled={passengers >= 9}
              />
            </div>
          </Field>
        </div>

        {/* --- the answer ----------------------------------------------- */}
        <div className={`${s.calcResult}`} aria-live="polite">
          {results.length === 0 ? (
            <p className="text-body" style={{ color: "var(--text-on-ink-dim)" }}>
              {c.nothingYet}
            </p>
          ) : (
            <>
              <p className="text-micro uppercase" style={{ color: "var(--color-teal-400)" }}>
                {c.result}
              </p>
              <div className="mt-5 grid gap-4">
                {results.map((r) => (
                  <div key={r.key}>
                    <p className="text-caption" style={{ color: "var(--text-on-ink-dim)" }}>
                      {c.under} {LAW_NAME[r.key] ?? r.key}
                    </p>
                    <p className={`${s.code} text-display`} style={{ fontSize: "2.2rem" }}>
                      {r.symbol}
                      {r.total.toLocaleString("en-US")}
                    </p>
                    <p className="text-caption" style={{ color: "var(--text-on-ink-dim)" }}>
                      {passengers > 1
                        ? `${c.total} · ${r.symbol}${r.each.toLocaleString("en-US")} ${c.perPassenger}`
                        : c.perPassenger}
                    </p>
                  </div>
                ))}
              </div>

              {event === "DELAYED" ? (
                <p className={`${s.calcNote} mt-6`}>{c.delayNote}</p>
              ) : null}

              <p className="mt-6 text-caption" style={{ color: "var(--text-on-ink-dim)", lineHeight: 1.7 }}>
                {c.caveat}
              </p>

              <Link
                href="/#check"
                className={`${s.ctaOnInk} ${s.ctaPill} press mt-7 w-full justify-center px-6 py-3.5 text-subhead`}
              >
                {c.cta}
              </Link>
            </>
          )}
        </div>
      </div>
    </section>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <fieldset className="mb-8 last:mb-0">
      <legend className="text-subhead font-bold" style={{ color: "var(--text-strong)" }}>
        {label}
      </legend>
      {hint ? (
        <p className="mb-3 mt-1 text-caption" style={{ color: "var(--text-muted)" }}>
          {hint}
        </p>
      ) : (
        <div className="mb-3" />
      )}
      {children}
    </fieldset>
  );
}

function Stepper({
  onClick,
  label,
  disabled,
}: {
  onClick: () => void;
  label: string;
  disabled: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={label === "+" ? "נוסע נוסף" : "נוסע אחד פחות"}
      className={`${s.stepper} press`}
    >
      {label}
    </button>
  );
}
