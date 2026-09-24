"use client";

import Link from "next/link";
import { useState } from "react";

import { strings } from "@/lib/strings";

import s from "./hero.module.css";

/**
 * "How many of you were on the booking?" — asked on the RESULT screen.
 *
 * WHY HERE AND NOT IN THE CLAIM FORM
 * ----------------------------------
 * Compensation is per passenger, and the single most under-appreciated fact
 * about it is that a family of four is owed four times the figure on screen.
 * Asked later, deep in a form, it is a field. Asked here, next to the amount,
 * it CHANGES the amount in front of somebody who is deciding whether this is
 * worth their afternoon -- and ₪14,680 is a different decision from ₪3,670.
 *
 * The number travels to the claim as a query parameter, so the wizard opens
 * with the right number of passenger rows rather than asking again. Being
 * asked the same question twice is how a form starts to feel like paperwork.
 */
export function PassengerCount({
  checkId,
  amount,
  currency,
}: {
  checkId: string;
  amount: number | null;
  currency: string | null;
}) {
  const [count, setCount] = useState(1);
  const r = strings.result;

  const symbol = { ILS: "₪", EUR: "€", GBP: "£" }[currency ?? ""] ?? "";
  const total = amount !== null ? amount * count : null;

  return (
    <div className={`${s.countCard} mt-10`}>
      <div className="flex flex-wrap items-center justify-between gap-5">
        <div>
          <p className="text-subhead font-bold" style={{ color: "var(--text-strong)" }}>
            {r.howMany}
          </p>
          <p className="mt-1 text-caption" style={{ color: "var(--text-muted)" }}>
            {r.howManyHint}
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => setCount((n) => Math.max(1, n - 1))}
            disabled={count <= 1}
            aria-label="נוסע אחד פחות"
            className={`${s.stepper} press`}
          >
            −
          </button>
          <span
            className={`${s.code} w-10 text-center text-title`}
            style={{ color: "var(--text-strong)" }}
            aria-live="polite"
          >
            {count}
          </span>
          <button
            type="button"
            onClick={() => setCount((n) => Math.min(9, n + 1))}
            disabled={count >= 9}
            aria-label="נוסע נוסף"
            className={`${s.stepper} press`}
          >
            +
          </button>
        </div>
      </div>

      {total !== null && count > 1 ? (
        <p className="mt-5 text-title" style={{ color: "var(--color-teal-600)" }}>
          <span className={s.code}>
            {symbol}
            {total.toLocaleString("en-US", { minimumFractionDigits: 2 })}
          </span>{" "}
          <span className="text-callout" style={{ color: "var(--text-muted)" }}>
            {r.totalFor.replace("{n}", String(count))}
          </span>
        </p>
      ) : null}

      <Link
        href={`/claim/${checkId}?passengers=${count}`}
        className={`${s.cta} press mt-6 w-full justify-center px-7 py-4 text-subhead no-underline`}
        style={{ fontWeight: 700 }}
      >
        {r.startClaim}
      </Link>
    </div>
  );
}
