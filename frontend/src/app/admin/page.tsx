/**
 * The operator's screen.
 *
 * WHAT THIS IS, AND WHAT IT DELIBERATELY IS NOT
 *
 * It is a view over the same database the application writes to. It is NOT
 * a second service that listens and keeps its own copy.
 *
 * A copy can be stale, can miss rows while it restarts, and can disagree
 * with the original -- so "have we captured everything?" would stop being a
 * fact about the database and become a question about whether some process
 * was running last Tuesday. Reading the rows directly cannot be behind,
 * because there is nothing to be behind.
 *
 * HOW IT IS BUILT TO BE USED
 *
 * The motion this screen is designed around is not "read one customer". It
 * is "scan the list, open one, glance, close, open the next" -- so the
 * detail is a slide-over rather than a page, and closing it returns the
 * operator to the same scroll position, the same search and the same
 * filter. A page navigation would throw all three away every time.
 *
 * Rendered entirely in the browser, and the shell is a STATIC file on
 * purpose: every row is fetched client-side with the operator's key, so the
 * prerendered HTML holds no customer data and no secret. It is an empty
 * page with a password box.
 */

"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  customerStats,
  listCustomers,
  setClaimStatus,
  setCustomersHidden,
  type ClaimStatus,
  type CustomerCounts,
  type CustomerRow,
} from "@/lib/api";
import { useAdminKey } from "@/lib/session-key";
import { strings } from "@/lib/strings";
import { Toast, useToast } from "./Toast";
import s from "./crm.module.css";

const PAGE = 50;

/**
 * Open one customer in a NEW TAB.
 *
 * It used to be a slide-over, which is right for "glance and close" and
 * wrong for the job this screen is actually for: an operator with the
 * airline's form open in one tab and the customer in another, copying
 * fields across. A panel cannot be kept open, bookmarked, or pasted to
 * a colleague.
 *
 * `noopener` because a new tab opened with `window.open` can otherwise
 * reach back through `window.opener` and navigate the page it came from.
 * This is our own origin, so it is not an attack -- it is just a handle
 * nothing needs, and leaving it means the two tabs share a process.
 */
function openCustomer(checkId: string): void {
  window.open(`/admin/customers/${checkId}`, "_blank", "noopener");
}

export default function AdminPage() {
  const [key, setKey] = useAdminKey();
  if (key === null) return <KeyGate onKey={setKey} />;
  return <Console adminKey={key} onSignOut={() => setKey(null)} />;
}

// --- the gate ----------------------------------------------------------------

/** Nothing is fetched until a key is present -- not even the row count. */
function KeyGate({ onKey }: { onKey: (key: string) => void }) {
  const t = strings.admin;
  const [value, setValue] = useState("");

  return (
    <main className={s.gate}>
      <div className={s.gateCard}>
        <h1 className={s.gateTitle}>{t.title}</h1>
        <p className={s.gateText}>{t.keyExplain}</p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const trimmed = value.trim();
            if (trimmed) onKey(trimmed);
          }}
        >
          <label className={s.label} htmlFor="admin-key">
            {t.keyPrompt}
          </label>
          <input
            id="admin-key"
            className={s.input}
            type="password"
            autoComplete="off"
            value={value}
            onChange={(e) => setValue(e.target.value)}
          />
          <button
            type="submit"
            className={s.primary}
            style={{ marginTop: "1rem", width: "100%" }}
          >
            {t.enter}
          </button>
        </form>
      </div>
    </main>
  );
}

// --- the console -------------------------------------------------------------

type Filter = "all" | "claim" | "noClaim" | "review";

function Console({
  adminKey,
  onSignOut,
}: {
  adminKey: string;
  onSignOut: () => void;
}) {
  const t = strings.admin;
  const [rows, setRows] = useState<CustomerRow[]>([]);
  const [counts, setCounts] = useState<CustomerCounts | null>(null);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [anonymous, setAnonymous] = useState(false);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [bin, setBin] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [cursor, setCursor] = useState(-1);
  const toast = useToast();
  const searchBox = useRef<HTMLInputElement>(null);
  /**
   * Which request is the current one. The same race as on the archive
   * screen: one request per keystroke, answers arriving out of order, and
   * a stale failure landing after a fresh success. Here it is worse --
   * the stale path can call `onSignOut` and throw the operator back to
   * the key gate while they are mid-search.
   */
  const latest = useRef(0);

  /**
   * Change what the list shows, and drop the selection with it.
   *
   * A selection must never outlive the rows it was made on: ticks kept
   * across a filter change mean pressing delete acts on people who are no
   * longer on screen, which is the worst surprise a bulk action can
   * deliver.
   *
   * Done here, in the handler, rather than in an effect watching the
   * filters. Clearing is a consequence of the operator's action, not a
   * state to be synchronised afterwards -- and an effect would also fire
   * on the first render, for no reason.
   */
  const narrow = useCallback((change: () => void) => {
    setSelected(new Set());
    setCursor(-1);
    change();
  }, []);

  const load = useCallback(
    async (offset: number) => {
      const ticket = ++latest.current;
      setLoading(true);
      const result = await listCustomers(adminKey, {
        search: search.trim() || undefined,
        verdict: filter === "review" ? "NEEDS_REVIEW" : undefined,
        hasClaim:
          filter === "claim" ? true : filter === "noClaim" ? false : undefined,
        includeAnonymous: anonymous,
        hidden: bin,
        limit: PAGE,
        offset,
      });
      if (ticket !== latest.current) return;
      setLoading(false);
      if (!result.ok) {
        // A rejected key sends the operator back to the gate. Showing an
        // empty table instead would read as "there are no customers",
        // which is the most misleading thing this screen could say.
        // `denied` covers a wrong key and a server with none configured.
        // It used to fall through to `unreachable`, so an operator whose
        // key had been changed was told the service was down and had no
        // reason to try signing in again.
        if (
          result.failure.kind === "denied" ||
          result.failure.kind === "refused" ||
          result.failure.kind === "notFound"
        ) {
          return onSignOut();
        }
        return setFailed(true);
      }
      setFailed(false);
      setTotal(result.data.total);
      setRows((prev) =>
        offset === 0 ? result.data.items : [...prev, ...result.data.items],
      );
    },
    [adminKey, search, filter, anonymous, bin, onSignOut],
  );

  // Debounced: this fires on every keystroke, and each one is a query over
  // two joined tables.
  useEffect(() => {
    const timer = setTimeout(() => void load(0), 220);
    return () => clearTimeout(timer);
  }, [load]);

  // The counters do not depend on the search or the filter -- they are what
  // the filters narrow FROM -- so they are fetched per visibility setting
  // rather than on every keystroke.
  const refreshCounts = useCallback(() => {
    void customerStats(adminKey, anonymous).then((r) => {
      if (r.ok) setCounts(r.data);
    });
  }, [adminKey, anonymous]);

  useEffect(refreshCounts, [refreshCounts]);

  const afterWrite = useCallback(() => {
    setSelected(new Set());
    void load(0);
    refreshCounts();
  }, [load, refreshCounts]);

  /**
   * Hide or restore, with the undo attached to the result.
   *
   * No "are you sure?" first. A confirmation shown every time is one
   * people learn to click through without reading, so it protects nobody
   * and taxes the ninety-nine harmless cases. Acting at once and offering
   * a way back is the better trade -- and only possible because hiding
   * does not destroy anything.
   */
  const move = useCallback(
    async (ids: string[], hidden: boolean) => {
      const result = await setCustomersHidden(adminKey, ids, hidden);
      if (!result.ok) {
        return toast.show({ text: t.toast.failed, tone: "bad" });
      }
      const moved = result.data.moved;
      afterWrite();
      toast.show({
        // The number the SERVER reports, not the number selected. If six
        // were already hidden, saying "50 removed" is a small lie the
        // operator will eventually catch.
        text: hidden ? t.toast.hidden(moved) : t.toast.restored(moved),
        undoLabel: t.toast.undo,
        undo: () => void move(ids, !hidden),
      });
    },
    [adminKey, afterWrite, toast, t],
  );

  const exportCsv = useCallback(() => {
    const chosen = selected.size
      ? rows.filter((r) => selected.has(r.check_id))
      : rows;
    downloadCsv(chosen);
  }, [rows, selected]);

  // Keyboard. An operator working a list of names keeps their hands where
  // they are; every one of these replaces a reach for the mouse.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const typing =
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        target instanceof HTMLSelectElement;

      if (e.key === "/" && !typing) {
        e.preventDefault();
        return searchBox.current?.focus();
      }
      // Escape clears the search box when it is focused, and otherwise
      // drops the selection -- both are "undo the thing I just narrowed".
      if (e.key === "Escape" && typing) {
        return (target as HTMLInputElement).blur();
      }
      if (typing) return;
      if (e.key === "Escape") return setSelected(new Set());
      if (e.key === "ArrowDown" || e.key === "j") {
        e.preventDefault();
        return setCursor((c) => Math.min(c + 1, rows.length - 1));
      }
      if (e.key === "ArrowUp" || e.key === "k") {
        e.preventDefault();
        return setCursor((c) => Math.max(c - 1, 0));
      }
      if (e.key === "Enter" && cursor >= 0 && rows[cursor]) {
        return openCustomer(rows[cursor].check_id);
      }
      if (e.key === "x" && cursor >= 0 && rows[cursor]) {
        e.preventDefault();
        return toggle(rows[cursor].check_id);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [rows, cursor]);

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const allShown = rows.length > 0 && rows.every((r) => selected.has(r.check_id));

  return (
    <div className={s.page}>
      <header className={s.bar}>
        <div className={s.barInner}>
          <nav className={s.tabs}>
            <Link href="/admin" className={`${s.tab} ${s.tabOn}`}>
              {t.flights.customersTab}
            </Link>
            <Link href="/admin/flights" className={s.tab}>
              {t.flights.tab}
            </Link>
          </nav>

          <div className={s.search}>
            <span className={s.searchIcon} aria-hidden>
              <SearchIcon />
            </span>
            <input
              ref={searchBox}
              className={s.searchInput}
              type="search"
              value={search}
              onChange={(e) => narrow(() => setSearch(e.target.value))}
              placeholder={t.searchPlaceholder}
              aria-label={t.searchPlaceholder}
            />
          </div>

          <div className={s.segmented} role="group" aria-label={t.filterGroup}>
            {(
              [
                ["all", t.filters.all],
                ["claim", t.filters.withClaim],
                ["noClaim", t.filters.withoutClaim],
                ["review", t.filters.review],
              ] as const
            ).map(([value, label]) => (
              <button
                key={value}
                type="button"
                aria-pressed={filter === value}
                className={`${s.segment} ${filter === value ? s.segmentOn : ""}`}
                onClick={() => narrow(() => setFilter(value))}
              >
                {label}
              </button>
            ))}
          </div>

          <button
            type="button"
            className={s.ghost}
            aria-pressed={bin}
            onClick={() => narrow(() => setBin((b) => !b))}
            title={t.binNote}
          >
            {t.binView}
          </button>

          <button type="button" className={s.ghost} onClick={onSignOut}>
            {t.signOut}
          </button>
        </div>
      </header>

      {/* The bulk bar REPLACES the counters rather than appearing under
          them, so ticking a box does not push the whole table down the
          screen while the operator is reading it. */}
      {selected.size > 0 ? (
        <div className={s.bulk}>
          <div className={s.bulkInner}>
            <span className={s.bulkCount}>
              {selected.size === 1 ? t.select.one : t.select.many(selected.size)}
            </span>
            <button
              type="button"
              className={s.bulkButton}
              onClick={() => setSelected(new Set())}
            >
              {t.select.clear}
            </button>
            <button type="button" className={s.bulkButton} onClick={exportCsv}>
              {t.select.exportCsv}
            </button>
            <span className={s.spacer} />
            <button
              type="button"
              className={`${s.bulkButton} ${bin ? "" : s.bulkDanger}`}
              onClick={() => void move([...selected], !bin)}
            >
              {bin ? t.select.restore : t.select.delete}
            </button>
          </div>
        </div>
      ) : (
        <div className={s.counts}>
          <Count label={t.counts.total} value={counts?.total} />
          <Count label={t.counts.eligible} value={counts?.eligible} tone="yes" />
          <Count label={t.counts.review} value={counts?.review} tone="review" />
          <Count label={t.counts.claims} value={counts?.claims} />
        </div>
      )}

      {bin && (
        <div className={s.counts}>
          <p className={s.note}>{t.binNote}</p>
        </div>
      )}

      <main className={s.sheet}>
        <div className={s.card}>
          {failed ? (
            <p className={s.empty}>{t.failed}</p>
          ) : loading && rows.length === 0 ? (
            <SkeletonTable />
          ) : rows.length === 0 ? (
            <p className={s.empty}>{t.empty}</p>
          ) : (
            <div className={s.scroll}>
              <table className={s.table}>
                <thead>
                  <tr>
                    <th className={`${s.th} ${s.checkCell}`}>
                      <input
                        type="checkbox"
                        checked={allShown}
                        aria-label={t.select.selectAll}
                        onChange={(e) =>
                          setSelected(
                            e.target.checked
                              ? new Set(rows.map((r) => r.check_id))
                              : new Set(),
                          )
                        }
                      />
                    </th>
                    <th className={s.th}>{t.columns.customer}</th>
                    <th className={s.th}>{t.columns.flight}</th>
                    <th className={s.th}>{t.columns.date}</th>
                    <th className={s.th}>{t.columns.email}</th>
                    <th className={s.th}>{t.columns.phone}</th>
                    <th className={s.th}>{t.columns.verdict}</th>
                    <th className={s.th}>{t.columns2.stage}</th>
                    <th className={s.th}>{t.columns.amount}</th>
                    <th className={s.th}>{t.columns.files}</th>
                    <th className={s.th}>{t.columns2.when}</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row, i) => (
                    <Row
                      key={row.check_id}
                      row={row}
                      adminKey={adminKey}
                      selected={selected.has(row.check_id)}
                      focused={i === cursor}
                      onToggle={() => toggle(row.check_id)}
                      onOpen={() => openCustomer(row.check_id)}
                      onStageSaved={() => {
                        toast.show({ text: t.toast.stageSaved });
                        void load(0);
                      }}
                      onCopied={() => toast.show({ text: t.toast.copied })}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {rows.length > 0 && (
          <div className={s.footer}>
            <span className={s.footerCount}>{t.showing(rows.length, total)}</span>
            {rows.length < total && (
              <button
                type="button"
                className={s.ghost}
                disabled={loading}
                onClick={() => void load(rows.length)}
              >
                {t.loadMore}
              </button>
            )}
            <button type="button" className={s.ghost} onClick={exportCsv}>
              {t.select.exportCsv}
            </button>
            <span className={s.spacer} />
            <span className={s.hint}>{t.shortcuts.hint}</span>
            <label className={s.chip}>
              <input
                type="checkbox"
                checked={anonymous}
                onChange={(e) => narrow(() => setAnonymous(e.target.checked))}
              />
              {t.filters.anonymous}
            </label>
          </div>
        )}
      </main>

      <Toast message={toast.message} onDismiss={toast.dismiss} />

    </div>
  );
}

function Count({
  label,
  value,
  tone,
}: {
  label: string;
  value: number | undefined;
  tone?: "yes" | "review";
}) {
  const toneClass =
    tone === "yes" ? s.countValueYes : tone === "review" ? s.countValueReview : "";
  return (
    <div className={s.count}>
      <div className={`${s.countValue} ${toneClass}`}>
        {/* An em dash while loading, never 0. A zero that becomes 47 is a
            number the operator has already read and believed. */}
        {value === undefined ? "—" : value.toLocaleString("he-IL")}
      </div>
      <div className={s.countLabel}>{label}</div>
    </div>
  );
}

function Row({
  row,
  adminKey,
  selected,
  focused,
  onToggle,
  onOpen,
  onStageSaved,
  onCopied,
}: {
  row: CustomerRow;
  adminKey: string;
  selected: boolean;
  focused: boolean;
  onToggle: () => void;
  onOpen: () => void;
  onStageSaved: () => void;
  onCopied: () => void;
}) {
  const ref = useRef<HTMLTableRowElement>(null);

  // Keyboard navigation has to bring the row with it. `block: "nearest"`
  // rather than "center": an operator stepping down a list wants the next
  // row, not the whole table re-centring under them on every press.
  useEffect(() => {
    if (focused) ref.current?.scrollIntoView({ block: "nearest" });
  }, [focused]);

  return (
    <tr
      ref={ref}
      className={`${s.row} ${selected ? s.rowSelected : ""}`}
      tabIndex={0}
      role="button"
      style={focused ? { outline: "2px solid var(--border-focus)", outlineOffset: "-2px" } : undefined}
      onClick={onOpen}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onOpen();
        }
      }}
    >
      {/* Everything in this cell stops propagation: the whole row opens the
          customer, and a tick, a copy or a stage change must not also throw
          a panel over the list the operator is working through. */}
      <td
        className={`${s.td} ${s.checkCell}`}
        onClick={(e) => e.stopPropagation()}
      >
        <input
          type="checkbox"
          checked={selected}
          onChange={onToggle}
          aria-label={row.contact_name ?? row.flight_number}
        />
      </td>
      <td className={`${s.td} ${s.name}`}>{row.contact_name || "—"}</td>
      <td className={s.td}>
        <span className={s.num}>{row.flight_number}</span>
      </td>
      <td className={s.td}>
        <span className={s.num}>{row.flight_date}</span>
      </td>
      <td className={s.td} onClick={(e) => e.stopPropagation()}>
        {row.contact_email ? (
          <Copyable value={row.contact_email} onCopied={onCopied} />
        ) : (
          <Dash />
        )}
      </td>
      <td className={s.td} onClick={(e) => e.stopPropagation()}>
        {row.contact_phone ? (
          <Copyable value={row.contact_phone} mono onCopied={onCopied} />
        ) : (
          <Dash />
        )}
      </td>
      <td className={s.td}>
        <Pill verdict={row.verdict} />
      </td>
      <td className={s.td} onClick={(e) => e.stopPropagation()}>
        <Stage row={row} adminKey={adminKey} onSaved={onStageSaved} />
      </td>
      <td className={s.td}>
        {row.best_amount ? (
          <span className={s.amount}>
            {money(row.best_amount, row.best_currency)}
          </span>
        ) : (
          <Dash />
        )}
      </td>
      <td className={s.td}>
        {row.document_count > 0 ? (
          <span className={s.chip}>
            <ClipIcon /> {row.document_count}
          </span>
        ) : (
          <Dash />
        )}
      </td>
      <td className={`${s.td} ${s.muted}`}>{ago(row.created_at)}</td>
    </tr>
  );
}

/**
 * The claim's stage, editable in place.
 *
 * All eight stages already existed in the model and nothing could set
 * them, so the column only ever read DRAFT or SUBMITTED whatever had
 * really happened -- and an operator with a decorative status column keeps
 * the real one in a spreadsheet, where this system cannot see it.
 *
 * A plain <select>, styled to look like text until hovered. The column is
 * scanned far more often than it is changed, so at rest it should read as
 * data rather than as a form.
 */
function Stage({
  row,
  adminKey,
  onSaved,
}: {
  row: CustomerRow;
  adminKey: string;
  onSaved: () => void;
}) {
  const t = strings.admin;
  // Optimistic: the select shows the new value immediately and rolls back
  // if the server refuses. A dropdown that snaps back to the old value for
  // half a second on every change feels broken even when it works.
  const [value, setValue] = useState(row.claim_status);
  const [busy, setBusy] = useState(false);

  if (!row.claim_id) return <Dash />;

  const tone =
    value === "SETTLED"
      ? s.stageSettled
      : value === "REJECTED" || value === "WITHDRAWN"
        ? s.stageRejected
        : value === "AWAITING_AIRLINE" || value === "SENT_TO_AIRLINE"
          ? s.stageWaiting
          : "";

  return (
    <select
      className={`${s.stage} ${tone}`}
      value={value ?? ""}
      disabled={busy}
      onChange={(e) => {
        const next = e.target.value as ClaimStatus;
        const previous = value;
        setValue(next);
        setBusy(true);
        void setClaimStatus(adminKey, row.claim_id!, next).then((r) => {
          setBusy(false);
          if (r.ok) onSaved();
          else setValue(previous);
        });
      }}
    >
      {t.stageOrder.map((stage) => (
        <option key={stage} value={stage}>
          {t.stages[stage]}
        </option>
      ))}
    </select>
  );
}

/**
 * A value that copies itself when clicked.
 *
 * The thing an operator does with an email address on this screen is put
 * it somewhere else -- a reply, a form, the airline's portal. Selecting
 * text in a table row is fiddly and, since the row is itself a button,
 * a drag-select would open the panel instead.
 */
function Copyable({
  value,
  mono,
  onCopied,
}: {
  value: string;
  mono?: boolean;
  onCopied: () => void;
}) {
  return (
    <button
      type="button"
      className={`${s.copy} ${mono ? s.num : ""}`}
      title={value}
      onClick={() => {
        void navigator.clipboard?.writeText(value).then(onCopied, () => {});
      }}
    >
      {value}
    </button>
  );
}

function Dash() {
  return <span className={s.muted}>—</span>;
}

function Pill({ verdict }: { verdict: string | null }) {
  const t = strings.admin;
  if (!verdict)
    return <span className={`${s.pill} ${s.pillNo}`}>{t.noVerdict}</span>;
  const tone =
    verdict === "ELIGIBLE" || verdict === "LIKELY_ELIGIBLE"
      ? s.pillYes
      : verdict === "NEEDS_REVIEW"
        ? s.pillReview
        : s.pillNo;
  return (
    <span className={`${s.pill} ${tone}`}>{t.verdicts[verdict] ?? verdict}</span>
  );
}

const SYMBOL: Record<string, string> = { EUR: "€", GBP: "£", ILS: "₪" };

function money(amount: string, currency: string | null): string {
  const symbol = currency ? (SYMBOL[currency] ?? `${currency} `) : "";
  return `${symbol}${Number(amount).toLocaleString("he-IL", {
    minimumFractionDigits: 2,
  })}`;
}

function SkeletonTable() {
  return (
    <div className={s.skeletonWrap}>
      {Array.from({ length: 8 }, (_, i) => (
        <div key={i} className={s.skeletonRow}>
          {Array.from({ length: 7 }, (_, j) => (
            <div key={j} className={s.skeleton} />
          ))}
        </div>
      ))}
    </div>
  );
}

/**
 * Hand the operator a spreadsheet of what is on screen.
 *
 * Exports the SELECTION if there is one, and the loaded rows otherwise --
 * matching what every other bulk action on this screen does, so "export"
 * never means something different from "delete".
 *
 * Two details that look fussy and are not:
 *
 *   The BOM. Without it Excel opens a UTF-8 file as the local 8-bit
 *   codepage, and every Hebrew name becomes mojibake. It is the single
 *   most common way a correct CSV arrives broken.
 *
 *   The apostrophe guard. A cell beginning =, +, - or @ is executed as a
 *   formula by Excel and Sheets, so a customer who types a name starting
 *   with "=" becomes a formula running on the operator's machine. Quoting
 *   does not prevent it; prefixing does.
 */
function downloadCsv(rows: CustomerRow[]): void {
  const t = strings.admin;
  const header = [
    t.columns.customer,
    t.columns.flight,
    t.columns.date,
    t.columns.email,
    t.columns.phone,
    t.columns.verdict,
    t.columns.amount,
    t.columns2.stage,
    t.detail.reference,
  ];
  const body = rows.map((r) => [
    r.contact_name ?? "",
    r.flight_number,
    r.flight_date,
    r.contact_email ?? "",
    r.contact_phone ?? "",
    r.verdict ? (t.verdicts[r.verdict] ?? r.verdict) : t.noVerdict,
    r.best_amount ? `${r.best_amount} ${r.best_currency ?? ""}`.trim() : "",
    r.claim_status ? (t.stages[r.claim_status] ?? r.claim_status) : "",
    r.claim_reference ?? "",
  ]);

  const csv = [header, ...body]
    .map((line) => line.map(cell).join(","))
    .join("\r\n");

  const blob = new Blob(["\uFEFF" + csv], {
    type: "text/csv;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `skyclaim-customers-${new Date().toISOString().slice(0, 10)}.csv`;
  anchor.click();
  URL.revokeObjectURL(url);
}

function cell(value: string): string {
  const guarded = /^[=+\-@]/.test(value) ? `'${value}` : value;
  return `"${guarded.replace(/"/g, '""')}"`;
}

/**
 * "20 minutes ago" rather than "14:32".
 *
 * An operator opening this wants to know what is NEW. A clock time makes
 * them do the subtraction; anything older than a week is a date again,
 * because "lefnei 23 yamim" is no longer a useful quantity.
 */
function ago(iso: string): string {
  const t = strings.admin.ago;
  const minutes = Math.floor((Date.now() - Date.parse(iso)) / 60000);
  if (minutes < 2) return t.now;
  if (minutes < 60) return t.minutes(minutes);
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return t.hours(hours);
  const days = Math.floor(hours / 24);
  if (days <= 7) return t.days(days);
  return iso.slice(0, 10);
}

// --- icons -------------------------------------------------------------------
//
// Inline rather than an icon package: there are two of them, and a
// dependency for two paths is a dependency to keep updated forever.

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

function ClipIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden>
      <path
        d="M10.5 4.5 5.9 9.1a1.6 1.6 0 0 0 2.3 2.3l4.9-4.9a3 3 0 0 0-4.3-4.3L3.6 7.4a4.5 4.5 0 0 0 6.4 6.4l4.2-4.2"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
