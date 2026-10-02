/**
 * The archive, read back exactly as the rules receive it.
 *
 * WHAT THIS SCREEN IS FOR
 *
 * One question, asked often: when a customer gets a strange answer, is it
 * the RULES being wrong or the DATA being thin?
 *
 * `app.tasks.find` has answered that from a terminal all through this
 * project -- BZ887, HM9349, A45024 and 6H502 were every one of them
 * diagnosed by reading the stored row rather than the code. This is the
 * same thing without the terminal.
 *
 * It shows both sources separately and never merges them, because when
 * the airport board and the commercial feed disagree, the disagreement
 * IS the bug. 6H502 was exactly that: the board had an arrival pair and
 * no departure, AeroDataBox had a departure and no arrival airport, and
 * neither alone explained the verdict.
 *
 * Every row expands to the raw payload. Derived fields are our reading of
 * the source; the raw payload is what the source actually said, and the
 * argument is only ever settled by seeing both.
 */

"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { searchArchive, type ArchivedFlight } from "@/lib/api";
import { useAdminKey } from "@/lib/session-key";
import { strings } from "@/lib/strings";
import { airportToday } from "@/lib/today";
import s from "../crm.module.css";

export default function FlightArchivePage() {
  const [key] = useAdminKey();
  const t = strings.admin;

  if (key === null) {
    // No key gate of its own: the customer screen owns that conversation,
    // and two places to type the same secret is one too many.
    return (
      <main className={s.gate}>
        <div className={s.gateCard}>
          <h1 className={s.gateTitle}>{t.flights.title}</h1>
          <p className={s.gateText}>{t.keyExplain}</p>
          <Link href="/admin" className={s.primary} style={{ display: "block", textAlign: "center", textDecoration: "none" }}>
            {t.enter}
          </Link>
        </div>
      </main>
    );
  }
  return <Archive adminKey={key} />;
}

function Archive({ adminKey }: { adminKey: string }) {
  const t = strings.admin;
  const [number, setNumber] = useState("");
  const [day, setDay] = useState("");
  const [disruptedOnly, setDisruptedOnly] = useState(true);
  const [rows, setRows] = useState<ArchivedFlight[]>([]);
  const [truncated, setTruncated] = useState(false);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [openRaw, setOpenRaw] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    const result = await searchArchive(adminKey, {
      number: number.trim() || undefined,
      date: day || undefined,
      // A flight number is a targeted lookup, and the reason to do one is
      // usually that the flight does NOT look disrupted. Filtering those
      // out would hide the answer the operator came for.
      disruptedOnly: number.trim() ? false : disruptedOnly,
      limit: 150,
    });
    setLoading(false);
    if (!result.ok) return setFailed(true);
    setFailed(false);
    setRows(result.data.items);
    setTruncated(result.data.truncated);
  }, [adminKey, number, day, disruptedOnly]);

  useEffect(() => {
    const timer = setTimeout(() => void load(), 250);
    return () => clearTimeout(timer);
  }, [load]);

  return (
    <div className={s.page}>
      <header className={s.bar}>
        <div className={s.barInner}>
          <nav className={s.tabs}>
            <Link href="/admin" className={s.tab}>
              {t.flights.customersTab}
            </Link>
            <Link href="/admin/flights" className={`${s.tab} ${s.tabOn}`}>
              {t.flights.tab}
            </Link>
          </nav>

          <div className={s.search}>
            <span className={s.searchIcon} aria-hidden>
              <SearchIcon />
            </span>
            <input
              className={s.searchInput}
              type="search"
              value={number}
              onChange={(e) => setNumber(e.target.value)}
              placeholder={t.flights.searchNumber}
              aria-label={t.flights.searchNumber}
            />
          </div>

          <input
            className={s.dateInput}
            type="date"
            value={day}
            // Flights are archived up to five days ahead of today, so the
            // cap is not today's date -- unlike the customer form, where a
            // future flight cannot have been delayed yet.
            max={addDays(airportToday(), 10)}
            onChange={(e) => setDay(e.target.value)}
            aria-label={t.flights.searchDate}
          />

          {(number || day) && (
            <button
              type="button"
              className={s.ghost}
              onClick={() => {
                setNumber("");
                setDay("");
              }}
            >
              {t.flights.clear}
            </button>
          )}

          <label className={s.chip}>
            <input
              type="checkbox"
              checked={disruptedOnly}
              disabled={!!number.trim()}
              onChange={(e) => setDisruptedOnly(e.target.checked)}
            />
            {t.flights.disruptedOnly}
          </label>
        </div>
      </header>

      <main className={s.sheet} style={{ marginTop: "1.25rem" }}>
        <p className={s.footerCount} style={{ marginBottom: "0.75rem" }}>
          {t.flights.lead}
        </p>

        <div className={s.card}>
          {failed ? (
            <p className={s.empty}>{t.failed}</p>
          ) : loading && rows.length === 0 ? (
            <p className={s.empty}>{t.files.loading}</p>
          ) : rows.length === 0 ? (
            <div className={s.empty}>
              <p style={{ margin: 0 }}>{t.flights.empty}</p>
              <p style={{ margin: "0.5rem 0 0", fontSize: "var(--text-caption)" }}>
                {t.flights.emptyHint}
              </p>
            </div>
          ) : (
            <div className={s.scroll}>
              <table className={s.table}>
                <thead>
                  <tr>
                    <th className={s.th}>{t.flights.columns.flight}</th>
                    <th className={s.th}>{t.flights.columns.date}</th>
                    <th className={s.th}>{t.flights.columns.route}</th>
                    <th className={s.th}>{t.flights.columns.scheduledDeparture}</th>
                    <th className={s.th}>{t.flights.columns.actualDeparture}</th>
                    <th className={s.th}>{t.flights.columns.scheduledArrival}</th>
                    <th className={s.th}>{t.flights.columns.actualArrival}</th>
                    <th className={s.th}>{t.flights.columns.status}</th>
                    <th className={s.th}>{t.flights.columns.source}</th>
                    <th className={s.th}>{t.flights.columns.usable}</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row, i) => {
                    const id = `${row.provider}-${row.flight_number}-${row.flight_date}-${i}`;
                    return (
                      <Row
                        key={id}
                        row={row}
                        open={openRaw === id}
                        onToggle={() => setOpenRaw(openRaw === id ? null : id)}
                      />
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {truncated && (
          <p className={s.footerCount} style={{ marginTop: "0.75rem" }}>
            {t.flights.truncated}
          </p>
        )}
        {rows.length > 0 && (
          <p className={s.footerCount} style={{ marginTop: "0.5rem" }}>
            {rows.length}
          </p>
        )}
      </main>
    </div>
  );
}

function Row({
  row,
  open,
  onToggle,
}: {
  row: ArchivedFlight;
  open: boolean;
  onToggle: () => void;
}) {
  const t = strings.admin;
  return (
    <>
      <tr className={s.row} onClick={onToggle} tabIndex={0} role="button"
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            onToggle();
          }
        }}
      >
        <td className={`${s.td} ${s.name}`}>
          <span className={s.num}>{row.flight_number}</span>
        </td>
        <td className={s.td}>
          <span className={s.num}>{row.flight_date}</span>
        </td>
        <td className={s.td}>
          <span className={s.num}>
            {row.origin_iata ?? "???"} → {row.destination_iata ?? "???"}
          </span>
        </td>
        <td className={s.td}>
          <Clock at={row.scheduled_departure} />
        </td>
        <td className={s.td}>
          <Clock at={row.actual_departure} delay={row.departure_delay_minutes} />
        </td>
        <td className={s.td}>
          <Clock at={row.scheduled_arrival} />
        </td>
        <td className={s.td}>
          <Clock at={row.actual_arrival} delay={row.arrival_delay_minutes} />
        </td>
        <td className={s.td}>
          {t.flights.statuses[row.status] ?? row.status}
        </td>
        <td className={s.td}>
          <span className={s.source}>{row.provider}</span>
        </td>
        <td className={s.td}>
          {row.usable ? (
            <span className={s.muted}>{t.flights.usableYes}</span>
          ) : (
            <span className={s.unusable}>{t.flights.usableNo}</span>
          )}
        </td>
      </tr>

      {open && (
        <tr className={s.rawRow}>
          <td className={s.td} colSpan={10} style={{ padding: 0, whiteSpace: "normal" }}>
            <div className={s.rawMeta}>
              <span>
                {t.flights.seen}: <span className={s.num}>{row.observed_at.slice(0, 16).replace("T", " ")}</span>
              </span>
              <span>{row.is_final ? t.flights.settled : t.flights.notSettled}</span>
              {row.distance_km != null && (
                <span>
                  {t.flights.distance}:{" "}
                  <span className={s.num}>{Math.round(row.distance_km)} km</span>
                </span>
              )}
            </div>
            {/* The reason, in full, when the rules could not use this
                record. It is the sentence a customer was shown. */}
            {row.unusable_reason && (
              <p className={s.rawMeta}>
                <span className={s.unusable}>{row.unusable_reason}</span>
              </p>
            )}
            <p className={s.rawMeta} style={{ paddingBottom: 0 }}>
              {t.flights.rawTitle}
            </p>
            <pre className={s.rawBox}>{JSON.stringify(row.raw, null, 2)}</pre>
          </td>
        </tr>
      )}
    </>
  );
}

/**
 * A time, or a visible absence.
 *
 * An em dash in a lighter colour rather than an empty cell: "we have no
 * departure time for this flight" is one of the most important things
 * this screen can say, and a blank space says it too quietly to notice
 * while scanning.
 */
function Clock({ at, delay }: { at: string | null; delay?: number | null }) {
  const t = strings.admin;
  if (!at) return <span className={`${s.clock} ${s.clockNone}`}>—</span>;

  const late = delay != null && delay > 0;
  const early = delay != null && delay < 0;
  return (
    <>
      <span
        className={`${s.clock} ${late ? s.clockLate : early ? s.clockEarly : ""}`}
      >
        {/* Stored UTC, shown as Ben Gurion sees it -- the board publishes
            local time and so does every boarding pass the operator will be
            comparing this against. */}
        {new Date(at).toLocaleTimeString("en-GB", {
          hour: "2-digit",
          minute: "2-digit",
          timeZone: "Asia/Jerusalem",
        })}
      </span>
      {delay != null && Math.abs(delay) >= 1 && (
        <span className={s.delay}>{t.flights.delayShort(delay)}</span>
      )}
    </>
  );
}

function addDays(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

function SearchIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden>
      <circle cx="7" cy="7" r="4.75" stroke="currentColor" strokeWidth="1.5" />
      <path
        d="M10.5 10.5 14 14"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </svg>
  );
}
