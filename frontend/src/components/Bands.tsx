"use client";

import { useState } from "react";

import { strings } from "@/lib/strings";

import s from "./hero.module.css";

/**
 * What the law pays, by distance.
 *
 * WHY THE FAMILY TOGGLE EARNS ITS PLACE
 * -------------------------------------
 * The single most misunderstood fact about this compensation is that it is
 * per PASSENGER, not per booking. Somebody reading "₪3,670" assumes that is
 * what a cancelled flight is worth to them, when a family of four is owed
 * four times it.
 *
 * A sentence saying so is read and forgotten. A number that changes when you
 * flip a switch is understood -- and ₪14,680 is a different decision from
 * ₪3,670 about whether to bother claiming.
 */

const FAMILY_SIZE = 4;

export function Bands() {
  const [family, setFamily] = useState(false);
  const b = strings.bands;

  return (
    <section id="bands" className={`${s.mist} px-5 py-20 sm:px-8 sm:py-24`}>
      <div className="mx-auto max-w-5xl">
        <div className="text-center">
          <h2 className="text-title" style={{ color: "var(--text-strong)" }}>
            {b.title}
          </h2>
          <p
            className="mx-auto mt-4 max-w-2xl text-body"
            style={{ color: "var(--text-muted)" }}
          >
            {b.lead}
          </p>
        </div>

        <div className="mt-8 flex items-center justify-center gap-3">
          <label className="flex cursor-pointer items-center gap-3 text-callout">
            <span style={{ color: "var(--text-default)" }}>{b.familyToggle}</span>
            <button
              type="button"
              role="switch"
              aria-checked={family}
              onClick={() => setFamily((on) => !on)}
              className="relative h-6 w-11 rounded-full transition-colors"
              style={{
                background: family
                  ? "var(--color-teal-600)"
                  : "var(--border-default)",
              }}
            >
              <span
                className="absolute top-0.5 block size-5 rounded-full bg-white transition-transform"
                style={{
                  // RTL: the knob starts at the inline start, which is the
                  // right-hand side, and travels left when switched on.
                  insetInlineStart: "0.125rem",
                  transform: family ? "translateX(-1.25rem)" : "none",
                }}
              />
            </button>
          </label>
        </div>

        <div className="mt-10 grid gap-5 md:grid-cols-3">
          {b.rows.map((row) => (
            <div key={row.range} className={s.bandCard}>
              <p className="text-callout" style={{ color: "var(--text-muted)" }}>
                {row.range}
              </p>
              <p
                className={`${s.code} mt-2 text-display`}
                style={{ color: "var(--color-teal-600)", fontSize: "2.25rem" }}
              >
                {family ? multiply(row.amount, FAMILY_SIZE) : row.amount}
              </p>
              <p className="text-caption" style={{ color: "var(--text-muted)" }}>
                {family ? `למשפחה של ${FAMILY_SIZE}` : b.perPassenger}
              </p>
              <div className="mt-5 flex flex-wrap justify-center gap-1.5">
                {row.places.map((place) => (
                  <span key={place} className={s.place}>
                    {place}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>

        <div className="mt-10 text-center">
          <a href="#check" className={`${s.cta} ${s.ctaPill} px-7 py-3.5 text-subhead`}>
            {b.cta}
          </a>
          <p className="mt-4 text-caption" style={{ color: "var(--text-muted)" }}>
            {b.updatedNote}
          </p>
          {family ? (
            <p className="mt-2 text-caption" style={{ color: "var(--text-muted)" }}>
              {b.familyCaveat}
            </p>
          ) : null}
        </div>
      </div>
    </section>
  );
}

/**
 * "₪1,530" times four, still looking like money.
 *
 * Parsed from the string rather than kept as a number beside it, so there is
 * ONE source for each amount. Two -- a number for arithmetic and a string for
 * display -- is two things to keep in step when the law changes its figures,
 * and they will be changed by someone editing the copy.
 */
function multiply(amount: string, by: number): string {
  const digits = amount.replace(/[^\d]/g, "");
  if (!digits) return amount;
  const total = Number(digits) * by;
  return `₪${total.toLocaleString("en-US")}`;
}
