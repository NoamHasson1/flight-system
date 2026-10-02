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

import { useCallback, useEffect, useRef, useState } from "react";

import {
  customerStats,
  downloadDocument,
  listCustomers,
  readCustomer,
  type CustomerCounts,
  type CustomerDetail,
  type CustomerRow,
} from "@/lib/api";
import { useAdminKey } from "@/lib/session-key";
import { strings } from "@/lib/strings";
import s from "./crm.module.css";

const PAGE = 50;

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
  const [open, setOpen] = useState<string | null>(null);

  const load = useCallback(
    async (offset: number) => {
      setLoading(true);
      const result = await listCustomers(adminKey, {
        search: search.trim() || undefined,
        verdict: filter === "review" ? "NEEDS_REVIEW" : undefined,
        hasClaim:
          filter === "claim" ? true : filter === "noClaim" ? false : undefined,
        includeAnonymous: anonymous,
        limit: PAGE,
        offset,
      });
      setLoading(false);
      if (!result.ok) {
        // A rejected key sends the operator back to the gate. Showing an
        // empty table instead would read as "there are no customers",
        // which is the most misleading thing this screen could say.
        if (
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
    [adminKey, search, filter, anonymous, onSignOut],
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
  useEffect(() => {
    void customerStats(adminKey, anonymous).then((r) => {
      if (r.ok) setCounts(r.data);
    });
  }, [adminKey, anonymous]);

  return (
    <div className={s.page}>
      <header className={s.bar}>
        <div className={s.barInner}>
          <h1 className={s.title}>{t.title}</h1>

          <div className={s.search}>
            <span className={s.searchIcon} aria-hidden>
              <SearchIcon />
            </span>
            <input
              className={s.searchInput}
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
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
                onClick={() => setFilter(value)}
              >
                {label}
              </button>
            ))}
          </div>

          <button type="button" className={s.ghost} onClick={onSignOut}>
            {t.signOut}
          </button>
        </div>
      </header>

      <div className={s.counts}>
        <Count label={t.counts.total} value={counts?.total} />
        <Count label={t.counts.eligible} value={counts?.eligible} tone="yes" />
        <Count label={t.counts.review} value={counts?.review} tone="review" />
        <Count label={t.counts.claims} value={counts?.claims} />
      </div>

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
                    <th className={s.th}>{t.columns.customer}</th>
                    <th className={s.th}>{t.columns.flight}</th>
                    <th className={s.th}>{t.columns.date}</th>
                    <th className={s.th}>{t.columns.email}</th>
                    <th className={s.th}>{t.columns.phone}</th>
                    <th className={s.th}>{t.columns.verdict}</th>
                    <th className={s.th}>{t.columns.amount}</th>
                    <th className={s.th}>{t.columns.files}</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <Row
                      key={row.check_id}
                      row={row}
                      onOpen={() => setOpen(row.check_id)}
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
            <span className={s.spacer} />
            <label className={s.chip}>
              <input
                type="checkbox"
                checked={anonymous}
                onChange={(e) => setAnonymous(e.target.checked)}
              />
              {t.filters.anonymous}
            </label>
          </div>
        )}
      </main>

      {open && (
        <DetailPanel
          adminKey={adminKey}
          checkId={open}
          onClose={() => setOpen(null)}
        />
      )}
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

function Row({ row, onOpen }: { row: CustomerRow; onOpen: () => void }) {
  return (
    <tr
      className={s.row}
      tabIndex={0}
      role="button"
      onClick={onOpen}
      onKeyDown={(e) => {
        // The whole row is the target, so it needs the keyboard behaviour a
        // real button would have had for free.
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onOpen();
        }
      }}
    >
      <td className={`${s.td} ${s.name}`}>{row.contact_name || "—"}</td>
      <td className={s.td}>
        <span className={s.num}>{row.flight_number}</span>
      </td>
      <td className={s.td}>
        <span className={s.num}>{row.flight_date}</span>
      </td>
      <td className={s.td}>{row.contact_email || <Dash />}</td>
      <td className={s.td}>
        {row.contact_phone ? (
          <span className={s.num}>{row.contact_phone}</span>
        ) : (
          <Dash />
        )}
      </td>
      <td className={s.td}>
        <Pill verdict={row.verdict} />
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
    </tr>
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
          {Array.from({ length: 6 }, (_, j) => (
            <div key={j} className={s.skeleton} />
          ))}
        </div>
      ))}
    </div>
  );
}

// --- the detail panel --------------------------------------------------------

function DetailPanel({
  adminKey,
  checkId,
  onClose,
}: {
  adminKey: string;
  checkId: string;
  onClose: () => void;
}) {
  const t = strings.admin;
  const [data, setData] = useState<CustomerDetail | null>(null);
  const [failed, setFailed] = useState(false);
  const panel = useRef<HTMLElement>(null);

  useEffect(() => {
    void readCustomer(adminKey, checkId).then((r) =>
      r.ok ? setData(r.data) : setFailed(true),
    );
  }, [adminKey, checkId]);

  // Escape closes it, and focus moves in when it opens. An operator working
  // a list reaches for Escape before the mouse, and a panel that ignores it
  // feels stuck; moving focus is also what makes a screen reader announce
  // the thing that just appeared.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    panel.current?.focus();
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <>
      <div className={s.scrim} onClick={onClose} aria-hidden />
      <aside
        ref={panel}
        className={s.panel}
        role="dialog"
        aria-modal="true"
        aria-label={t.detail.title}
        tabIndex={-1}
      >
        <div className={s.panelBar}>
          <button type="button" className={s.ghost} onClick={onClose}>
            {t.detail.close}
          </button>
        </div>

        <div className={s.panelBody}>
          {failed && <p className={s.error}>{t.failed}</p>}
          {!failed && !data && (
            <>
              <div
                className={s.skeleton}
                style={{ height: "2rem", width: "60%" }}
              />
              <div
                className={s.skeleton}
                style={{ height: "1rem", width: "40%", marginTop: "0.75rem" }}
              />
            </>
          )}
          {data && <Detail data={data} adminKey={adminKey} />}
        </div>
      </aside>
    </>
  );
}

function Detail({ data, adminKey }: { data: CustomerDetail; adminKey: string }) {
  const t = strings.admin;
  return (
    <>
      <h2 className={s.panelName}>{data.contact_name || "—"}</h2>
      <p className={s.panelMeta}>
        <span className={s.num}>{data.flight_number}</span>
        <span aria-hidden>·</span>
        <span className={s.num}>{data.flight_date}</span>
        <Pill verdict={data.verdict} />
        {data.best_amount && (
          <span className={s.amount}>
            {money(data.best_amount, data.best_currency)}
          </span>
        )}
      </p>

      <section className={s.section}>
        <h3 className={s.sectionTitle}>{t.detail.contact}</h3>
        <dl className={s.fields}>
          {data.contact_email && (
            <>
              <dt className={s.fieldLabel}>{t.columns.email}</dt>
              <dd className={s.fieldValue}>
                {/* A real mailto. The next thing an operator does after
                    reading this row is write to the person. */}
                <a className={s.link} href={`mailto:${data.contact_email}`}>
                  {data.contact_email}
                </a>
              </dd>
            </>
          )}
          {data.contact_phone && (
            <>
              <dt className={s.fieldLabel}>{t.columns.phone}</dt>
              <dd className={s.fieldValue}>
                <a className={s.link} href={`tel:${data.contact_phone}`}>
                  <span className={s.num}>{data.contact_phone}</span>
                </a>
              </dd>
            </>
          )}
        </dl>
      </section>

      {!data.claim_id ? (
        <section className={s.section}>
          <p className={s.note}>{t.detail.nothingSubmitted}</p>
        </section>
      ) : (
        <>
          <section className={s.section}>
            <h3 className={s.sectionTitle}>{t.detail.claim}</h3>
            <dl className={s.fields}>
              <Field label={t.detail.reference} value={data.claim_reference} mono />
              <Field
                label={t.detail.bookingReference}
                value={data.booking_reference}
                mono
              />
              <Field label={t.detail.airlineReason} value={data.airline_reason} />
              <Field
                label={t.detail.cancellationNotice}
                value={
                  data.cancellation_notice
                    ? (t.notice[data.cancellation_notice] ??
                      data.cancellation_notice)
                    : null
                }
              />
              <Field
                label={t.detail.state}
                value={
                  data.claim_submitted_at
                    ? t.detail.submitted
                    : t.detail.notSubmitted
                }
              />
            </dl>
          </section>

          {data.passengers.length > 0 && (
            <section className={s.section}>
              <h3 className={s.sectionTitle}>
                {t.detail.passengers} ({data.passengers.length})
              </h3>
              {data.passengers.map((p, i) => (
                <div key={i} className={s.item}>
                  <strong>{p.full_name}</strong>
                  {p.national_id && (
                    <span className={s.muted}>
                      {t.detail.nationalId}{" "}
                      <span className={s.num}>{p.national_id}</span>
                    </span>
                  )}
                  {p.is_minor && <span className={s.muted}>{t.detail.minor}</span>}
                </div>
              ))}
            </section>
          )}

          {data.expenses.length > 0 && (
            <section className={s.section}>
              <h3 className={s.sectionTitle}>{t.detail.expenses}</h3>
              {data.expenses.map((e) => (
                <div key={e.id} className={s.item}>
                  <span className={s.amount}>{money(e.amount, e.currency)}</span>
                  <span>{t.categories[e.category] ?? e.category}</span>
                  {e.description && (
                    <span className={s.muted}>{e.description}</span>
                  )}
                </div>
              ))}
              {Object.entries(data.expense_totals).map(([currency, sum]) => (
                <p key={currency} className={s.total}>
                  {t.detail.total} {money(sum, currency)}
                </p>
              ))}
            </section>
          )}

          <section className={s.section}>
            <h3 className={s.sectionTitle}>
              {t.detail.documents} ({data.documents.length})
            </h3>
            {data.documents.length === 0 ? (
              <p className={s.note}>{t.noFiles}</p>
            ) : (
              data.documents.map((d) => (
                <FileButton key={d.id} adminKey={adminKey} file={d} />
              ))
            )}
          </section>
        </>
      )}
    </>
  );
}

function Field({
  label,
  value,
  mono,
}: {
  label: string;
  value: string | null;
  mono?: boolean;
}) {
  if (!value) return null;
  return (
    <>
      <dt className={s.fieldLabel}>{label}</dt>
      <dd className={s.fieldValue}>
        {mono ? <span className={s.num}>{value}</span> : value}
      </dd>
    </>
  );
}

function FileButton({
  adminKey,
  file,
}: {
  adminKey: string;
  file: CustomerDetail["documents"][number];
}) {
  const t = strings.admin;
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  return (
    <>
      <button
        type="button"
        className={s.file}
        disabled={busy}
        onClick={() => {
          setBusy(true);
          setError(null);
          void downloadDocument(adminKey, file.id, file.original_filename).then(
            (r) => {
              setBusy(false);
              if (!r.ok) {
                setError(
                  r.failure.kind === "refused"
                    ? r.failure.message
                    : strings.errors.unreachable,
                );
              }
            },
          );
        }}
      >
        <ClipIcon />
        <span className={s.fileName}>{file.original_filename}</span>
        <span className={s.fileMeta}>
          {t.kinds[file.kind] ?? file.kind} ·{" "}
          {Math.max(1, Math.round(file.size_bytes / 1024))}KB
        </span>
      </button>
      {error && <p className={s.error}>{error}</p>}
    </>
  );
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
