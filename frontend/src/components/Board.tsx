"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { airlineName, cityName } from "@/lib/names";
import { strings } from "@/lib/strings";

import s from "./hero.module.css";

/**
 * The board of recently disrupted flights.
 *
 * WHY THIS IS THE MOST IMPORTANT SECTION ON THE PAGE
 * --------------------------------------------------
 * Everything else here is an argument. This is evidence. A visitor who finds
 * their own cancelled flight listed and priced, before typing anything, does
 * not need to be persuaded the service works.
 *
 * And it is REAL. Every row comes from `flight_lookups` -- the Ben Gurion
 * board, written into our own archive every fifteen minutes by a cron that
 * does not sleep. No API call, no quota, no hand-written table of
 * plausible-looking flights. That is why this page carries no "for
 * illustration only" line: it has nothing to disclaim.
 *
 * FAILURE IS SILENT, ON PURPOSE
 * -----------------------------
 * If the endpoint is unreachable the section renders nothing at all rather
 * than an error. This is marketing furniture on a landing page, not the
 * customer's answer about their flight -- and a red box on a shop window
 * costs more trust than an absent section costs information. The check form
 * above it still works, which is the thing that matters.
 */

type Row = {
  flight_number: string;
  flight_date: string;
  origin: string;
  destination: string;
  airline: string;
  status: "CANCELLED" | "DELAYED";
  delay_hours: number | null;
  verdict: string;
  amount: string | null;
};

type Board = { updated_at: string; days: number; rows: Row[] };

export function FlightBoard() {
  const [board, setBoard] = useState<Board | null>(null);
  const [filter, setFilter] = useState<"all" | "today" | "week">("all");
  const [query, setQuery] = useState("");

  useEffect(() => {
    let live = true;
    // 14 days covers the widest filter, so changing the filter never costs
    // another request -- the whole set is already here and filtering is a
    // client-side slice.
    fetch("/api/v1/disruptions?days=14", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => live && setBoard(data))
      .catch(() => {
        /* Silent. See the note at the top of this file. */
      });
    return () => {
      live = false;
    };
  }, []);

  const scroller = useRef<HTMLDivElement>(null);
  const [paused, setPaused] = useState(false);

  /**
   * The board scrolls itself, slowly, and stops when touched.
   *
   * WHY IT MOVES AT ALL
   * -------------------
   * A static table of cancellations is a table. A moving one is a departures
   * board, which is the object this is imitating and the reason a visitor
   * believes it is live. It is also the only honest way to show sixty rows in
   * the height of twelve.
   *
   * ONE PIXEL AT A TIME, NOT A SCROLL ANIMATION
   * -------------------------------------------
   * `scrollTop += 0.4` on every frame, via requestAnimationFrame, which is
   * the display's own clock. A CSS transform marquee would be smoother still
   * but cannot be grabbed: the moment somebody reaches for their own flight
   * the element is mid-transition and their scroll fights it.
   *
   * IT MUST YIELD IMMEDIATELY
   * -------------------------
   * Pointer in, or keyboard focus inside: it stops. Anything that keeps
   * moving while somebody is trying to read it is not a nice touch, it is an
   * interface refusing to be used. It resumes when they leave.
   *
   * AND IT LOOPS
   * ------------
   * At the bottom it returns to the top. Not a jump -- `behavior: smooth`, so
   * the return reads as the board cycling rather than as a glitch.
   */
  useEffect(() => {
    const el = scroller.current;
    if (!el || paused) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    let frame = 0;
    let resting = 0;

    const step = () => {
      frame = requestAnimationFrame(step);
      // A short pause at the top before setting off, so the first rows can
      // actually be read.
      if (resting > 0) {
        resting -= 1;
        return;
      }
      const atBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 1;
      if (atBottom) {
        el.scrollTo({ top: 0, behavior: "smooth" });
        resting = 180;
        return;
      }
      el.scrollTop += 0.4;
    };

    resting = 150;
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [paused, board]);

  const rows = useMemo(() => {
    if (!board) return [];
    /**
     * "Today" is measured from the BOARD's clock, not the browser's.
     *
     * Two reasons, and the second is the one that matters. A memo that reads
     * Date.now() is impure -- React may re-run it at any time and get a
     * different answer for the same inputs. And a visitor in another
     * timezone has a different idea of today than Ben Gurion does, so
     * filtering on their clock would hide this morning's cancellations from
     * somebody in New York looking for exactly those.
     */
    const asOf = Date.parse(board.updated_at);
    const today = new Date(asOf).toISOString().slice(0, 10);
    const weekAgo = new Date(asOf - 7 * 864e5).toISOString().slice(0, 10);
    const needle = query.trim().toUpperCase();

    return board.rows.filter((r) => {
      if (filter === "today" && r.flight_date !== today) return false;
      if (filter === "week" && r.flight_date < weekAgo) return false;
      if (!needle) return true;
      return (
        r.flight_number.includes(needle) ||
        r.origin.includes(needle) ||
        r.destination.includes(needle) ||
        cityName(r.destination).includes(query.trim()) ||
        airlineName(r.airline).includes(query.trim())
      );
    });
  }, [board, filter, query]);

  // Nothing to show and nothing to apologise for.
  if (!board || board.rows.length === 0) return null;

  const b = strings.board;

  return (
    <section id="board" className={`${s.board} px-5 py-20 sm:px-8 sm:py-24`}>
      <div className="mx-auto max-w-6xl">
        <div className="flex flex-wrap items-end justify-between gap-6">
          <div>
            <h2 className="text-title">{b.title}</h2>
            <p className="mt-2 text-body" style={{ color: "var(--text-on-ink-dim)" }}>
              {b.lead}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <span className={s.live}>{b.live}</span>
            <span className="text-caption" style={{ color: "var(--text-on-ink-dim)" }}>
              {b.updated} {relative(board.updated_at)}
            </span>
          </div>
        </div>

        <div className="mt-8 flex flex-wrap items-center justify-between gap-4">
          <div className="flex gap-2">
            {(["all", "today", "week"] as const).map((key) => (
              <button
                key={key}
                type="button"
                onClick={() => setFilter(key)}
                className={`${s.chip} ${filter === key ? s.chipOn : ""}`}
              >
                {b.filters[key]}
              </button>
            ))}
          </div>
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={b.search}
            aria-label={b.search}
            className="w-full rounded-full px-5 py-2.5 text-callout sm:w-80"
            style={{
              background: "rgb(255 255 255 / 0.06)",
              border: "1px solid rgb(255 255 255 / 0.12)",
              color: "var(--text-on-ink)",
            }}
          />
        </div>

        <div
          ref={scroller}
          className={`${s.boardScroll} mt-6`}
          onMouseEnter={() => setPaused(true)}
          onMouseLeave={() => setPaused(false)}
          onFocusCapture={() => setPaused(true)}
          onBlurCapture={() => setPaused(false)}
          onTouchStart={() => setPaused(true)}
          tabIndex={0}
          role="region"
          aria-label={b.title}
        >
          <table className={s.boardTable}>
            <thead>
              <tr>
                <th>{b.columns.flight}</th>
                <th>{b.columns.route}</th>
                <th>{b.columns.airline}</th>
                <th>{b.columns.date}</th>
                <th>{b.columns.status}</th>
                <th>{b.columns.award}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={`${r.flight_number}-${r.flight_date}`}>
                  <td>
                    <span className={`${s.code} font-bold`}>{r.flight_number}</span>
                  </td>
                  <td style={{ color: "var(--text-on-ink-dim)" }}>
                    {cityName(r.origin)} ← {cityName(r.destination)}
                  </td>
                  <td style={{ color: "var(--text-on-ink-dim)" }}>{airlineName(r.airline)}</td>
                  <td>
                    <span className={s.code} style={{ color: "var(--text-on-ink-dim)" }}>
                      {r.flight_date.slice(8, 10)}/{r.flight_date.slice(5, 7)}
                    </span>
                  </td>
                  <td>
                    <Status row={r} />
                  </td>
                  <td>
                    {r.amount ? (
                      <span style={{ color: "var(--color-teal-400)", fontWeight: 700 }}>
                        {b.upTo}{" "}
                        <span className={s.code}>{r.amount}</span>
                      </span>
                    ) : (
                      <span style={{ color: "var(--text-on-ink-dim)" }}>{b.needsCheck}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {rows.length === 0 ? (
            <p className="py-10 text-center text-callout" style={{ color: "var(--text-on-ink-dim)" }}>
              {b.empty}
            </p>
          ) : null}
        </div>

        <p className="mt-5 text-caption" style={{ color: "var(--text-on-ink-dim)" }}>
          {b.footnote}
        </p>
      </div>
    </section>
  );
}

function Status({ row }: { row: Row }) {
  const b = strings.board;
  if (row.status === "CANCELLED") {
    return (
      <span style={{ color: "#f2564d", fontWeight: 700 }}>{b.status.cancelled}</span>
    );
  }
  const hours = row.delay_hours ?? 0;
  const h = Math.floor(hours);
  const m = Math.round((hours - h) * 60);
  return (
    <span style={{ color: "#e8b339", fontWeight: 700 }}>
      {b.status.delayed}{" "}
      <span className={s.code}>
        {h}:{String(m).padStart(2, "0")}
      </span>
    </span>
  );
}

/** "לפני 3 דקות". Rounded, because precision here is noise. */
function relative(iso: string): string {
  const minutes = Math.max(0, Math.round((Date.now() - Date.parse(iso)) / 60000));
  if (minutes < 1) return "עכשיו";
  if (minutes < 60) return `לפני ${minutes} דקות`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `לפני ${hours} שעות`;
  return `לפני ${Math.round(hours / 24)} ימים`;
}
