/**
 * The operator's screen.
 *
 * WHAT THIS IS, AND WHAT IT DELIBERATELY IS NOT
 *
 * It is a view over the same database the application writes to. It is NOT
 * a second service that listens and keeps its own copy.
 *
 * That was the instinct, and it is worth writing down why it was not built:
 * a copy can be stale, can miss rows while it restarts, and can disagree
 * with the original -- so the question "have we captured everything?" would
 * stop being a fact about the database and start being a question about
 * whether some process was running last Tuesday. Reading the rows directly
 * cannot be behind, because there is nothing to be behind.
 *
 * Rendered entirely in the browser, and the shell is a STATIC file on
 * purpose. Every row is fetched client-side with the operator's key, so the
 * HTML that Next prerenders and any CDN caches contains no customer data and
 * no secret -- it is an empty page with a password box. Making it dynamic
 * would gain nothing and put the rendering on a server that has no key.
 *
 * (A `dynamic` export here would be ignored anyway: route segment config is
 * only read from server components, and this one is "use client".)
 */

"use client";

import { useCallback, useEffect, useState } from "react";

import { useAdminKey } from "@/lib/session-key";

import {
  downloadDocument,
  listCustomers,
  readCustomer,
  type CustomerDetail,
  type CustomerRow,
} from "@/lib/api";
import { strings } from "@/lib/strings";

const PAGE = 50;

export default function AdminPage() {
  const [key, setKey] = useAdminKey();

  if (key === null) return <KeyGate onKey={setKey} />;
  return <Customers adminKey={key} onSignOut={() => setKey(null)} />;
}

/** Nothing is fetched until a key is present -- not even the row count. */
function KeyGate({ onKey }: { onKey: (key: string) => void }) {
  const t = strings.admin;
  const [value, setValue] = useState("");

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = value.trim();
    if (trimmed) onKey(trimmed);
  }

  return (
    <main className="mx-auto max-w-md px-4 py-20">
      <h1 className="text-headline">{t.title}</h1>
      <p className="mt-3 text-body" style={{ color: "var(--text-muted)" }}>
        {t.keyExplain}
      </p>
      <form onSubmit={submit} className="mt-8">
        <label className="block text-label" htmlFor="admin-key">
          {t.keyPrompt}
        </label>
        <input
          id="admin-key"
          type="password"
          autoComplete="off"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          className="mt-2 w-full rounded-xl px-4 py-3"
          style={{
            background: "var(--surface-mist)",
            border: "1px solid var(--border-subtle)",
          }}
        />
        <button type="submit" className="btn-primary mt-4 w-full">
          {t.enter}
        </button>
      </form>
    </main>
  );
}

function Customers({
  adminKey,
  onSignOut,
}: {
  adminKey: string;
  onSignOut: () => void;
}) {
  const t = strings.admin;
  const [rows, setRows] = useState<CustomerRow[]>([]);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<"all" | "claim" | "noClaim">("all");
  const [anonymous, setAnonymous] = useState(false);
  const [busy, setBusy] = useState(true);
  const [failed, setFailed] = useState(false);
  const [open, setOpen] = useState<string | null>(null);

  const load = useCallback(
    async (offset: number) => {
      setBusy(true);
      const result = await listCustomers(adminKey, {
        search: search || undefined,
        hasClaim: filter === "all" ? undefined : filter === "claim",
        includeAnonymous: anonymous,
        limit: PAGE,
        offset,
      });
      setBusy(false);
      if (!result.ok) {
        // A wrong key must send the operator back to the gate rather than
        // showing an empty table, which reads as "no customers".
        if (result.failure.kind === "notFound" || result.failure.kind === "refused") {
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

  // Debounced, because this fires on every keystroke in the search box and
  // each one is a database query over two joined tables.
  useEffect(() => {
    const timer = setTimeout(() => void load(0), 250);
    return () => clearTimeout(timer);
  }, [load]);

  if (open) {
    return (
      <CustomerDetailView
        adminKey={adminKey}
        checkId={open}
        onBack={() => setOpen(null)}
      />
    );
  }

  return (
    <main className="mx-auto max-w-6xl px-4 py-12">
      <header className="flex items-baseline justify-between gap-4">
        <div>
          <h1 className="text-headline">{t.title}</h1>
          <p className="mt-1 text-body" style={{ color: "var(--text-muted)" }}>
            {t.lead}
          </p>
        </div>
        <button onClick={onSignOut} className="text-label underline">
          {t.signOut}
        </button>
      </header>

      <div className="mt-8 flex flex-wrap items-center gap-3">
        <input
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={t.searchPlaceholder}
          className="min-w-0 flex-1 rounded-xl px-4 py-2.5"
          style={{
            background: "var(--surface-mist)",
            border: "1px solid var(--border-subtle)",
          }}
        />
        {(
          [
            ["all", t.filters.all],
            ["claim", t.filters.withClaim],
            ["noClaim", t.filters.withoutClaim],
          ] as const
        ).map(([value, label]) => (
          <button
            key={value}
            onClick={() => setFilter(value)}
            className="rounded-full px-4 py-2 text-label"
            style={{
              background:
                filter === value ? "var(--accent)" : "var(--surface-mist)",
              color: filter === value ? "white" : "var(--text-muted)",
            }}
          >
            {label}
          </button>
        ))}
        <label className="flex items-center gap-2 text-label">
          <input
            type="checkbox"
            checked={anonymous}
            onChange={(e) => setAnonymous(e.target.checked)}
          />
          {t.filters.anonymous}
        </label>
      </div>

      {failed && (
        <p className="mt-8 text-body" style={{ color: "var(--verdict-no)" }}>
          {t.failed}
        </p>
      )}

      {!failed && rows.length === 0 && !busy && (
        <p className="mt-10 text-body" style={{ color: "var(--text-muted)" }}>
          {t.empty}
        </p>
      )}

      {rows.length > 0 && (
        <>
          <div className="mt-8 overflow-x-auto">
            <table className="w-full text-start">
              <thead>
                <tr style={{ color: "var(--text-muted)" }}>
                  {[
                    t.columns.customer,
                    t.columns.flight,
                    t.columns.date,
                    t.columns.email,
                    t.columns.phone,
                    t.columns.verdict,
                    t.columns.amount,
                    t.columns.actions,
                  ].map((label, i) => (
                    <th key={i} className="px-3 py-2 text-start text-label">
                      {label}
                    </th>
                  ))}
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

          <p className="mt-6 text-label" style={{ color: "var(--text-muted)" }}>
            {t.showing(rows.length, total)}
          </p>
          {rows.length < total && (
            <button
              onClick={() => void load(rows.length)}
              disabled={busy}
              className="btn-secondary mt-3"
            >
              {t.loadMore}
            </button>
          )}
        </>
      )}
    </main>
  );
}

function Row({
  row,
  onOpen,
}: {
  row: CustomerRow;
  onOpen: () => void;
}) {
  const t = strings.admin;
  return (
    <tr style={{ borderTop: "1px solid var(--border-subtle)" }}>
      <td className="px-3 py-3">{row.contact_name || "—"}</td>
      <td className="px-3 py-3 tabular">{row.flight_number}</td>
      <td className="px-3 py-3 tabular">{row.flight_date}</td>
      <td className="px-3 py-3">{row.contact_email || "—"}</td>
      <td className="px-3 py-3 tabular">{row.contact_phone || "—"}</td>
      <td className="px-3 py-3">
        <Verdict verdict={row.verdict} />
      </td>
      <td className="px-3 py-3 tabular">
        {row.best_amount ? `${row.best_amount} ${row.best_currency ?? ""}` : "—"}
      </td>
      <td className="px-3 py-3">
        <div className="flex gap-2">
          <button onClick={onOpen} className="text-label underline">
            {t.viewDetails}
          </button>
          {row.document_count > 0 && (
            <button onClick={onOpen} className="text-label underline">
              {t.viewFiles(row.document_count)}
            </button>
          )}
        </div>
      </td>
    </tr>
  );
}

function Verdict({ verdict }: { verdict: string | null }) {
  const t = strings.admin;
  if (!verdict) {
    return <span style={{ color: "var(--text-muted)" }}>{t.noVerdict}</span>;
  }
  const pays = verdict === "ELIGIBLE" || verdict === "LIKELY_ELIGIBLE";
  return (
    <span
      style={{
        color: pays
          ? "var(--verdict-yes)"
          : verdict === "NEEDS_REVIEW"
            ? "var(--verdict-maybe)"
            : "var(--text-muted)",
        fontWeight: pays ? 600 : 400,
      }}
    >
      {t.verdicts[verdict] ?? verdict}
    </span>
  );
}

function CustomerDetailView({
  adminKey,
  checkId,
  onBack,
}: {
  adminKey: string;
  checkId: string;
  onBack: () => void;
}) {
  const t = strings.admin;
  const [data, setData] = useState<CustomerDetail | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    void (async () => {
      const result = await readCustomer(adminKey, checkId);
      if (result.ok) setData(result.data);
      else setFailed(true);
    })();
  }, [adminKey, checkId]);

  if (failed) {
    return (
      <main className="mx-auto max-w-3xl px-4 py-12">
        <button onClick={onBack} className="text-label underline">
          {t.detail.back}
        </button>
        <p className="mt-6" style={{ color: "var(--verdict-no)" }}>
          {t.failed}
        </p>
      </main>
    );
  }
  if (!data) return <main className="mx-auto max-w-3xl px-4 py-12" />;

  return (
    <main className="mx-auto max-w-3xl px-4 py-12">
      <button onClick={onBack} className="text-label underline">
        {t.detail.back}
      </button>

      <h1 className="mt-6 text-headline">{data.contact_name || "—"}</h1>
      <p className="mt-1 text-body" style={{ color: "var(--text-muted)" }}>
        {data.flight_number} · {data.flight_date} · <Verdict verdict={data.verdict} />
      </p>

      <Section title={t.detail.contact}>
        <Field label={strings.admin.columns.email} value={data.contact_email} />
        <Field label={strings.admin.columns.phone} value={data.contact_phone} />
      </Section>

      {data.claim_id ? (
        <>
          <Section title={t.detail.claim}>
            <Field label={t.detail.reference} value={data.claim_reference} />
            <Field
              label={t.detail.bookingReference}
              value={data.booking_reference}
            />
            <Field label={t.detail.airlineReason} value={data.airline_reason} />
            <Field
              label={t.detail.cancellationNotice}
              value={data.cancellation_notice}
            />
            <Field
              label=""
              value={
                data.claim_submitted_at
                  ? t.detail.submitted
                  : t.detail.notSubmitted
              }
            />
          </Section>

          {data.passengers.length > 0 && (
            <Section title={t.detail.passengers}>
              {data.passengers.map((p, i) => (
                <p key={i} className="py-1">
                  {p.full_name}
                  {p.national_id && (
                    <span style={{ color: "var(--text-muted)" }}>
                      {" · "}
                      {t.detail.nationalId} {p.national_id}
                    </span>
                  )}
                  {p.is_minor && (
                    <span style={{ color: "var(--text-muted)" }}>
                      {" · "}
                      {t.detail.minor}
                    </span>
                  )}
                </p>
              ))}
            </Section>
          )}

          {data.expenses.length > 0 && (
            <Section title={t.detail.expenses}>
              {data.expenses.map((e) => (
                <p key={e.id} className="py-1">
                  <span className="tabular">
                    {e.amount} {e.currency}
                  </span>
                  {" · "}
                  {e.category}
                  {e.description && (
                    <span style={{ color: "var(--text-muted)" }}>
                      {" · "}
                      {e.description}
                    </span>
                  )}
                </p>
              ))}
              {Object.entries(data.expense_totals).map(([currency, total]) => (
                <p key={currency} className="pt-2 font-semibold tabular">
                  {t.detail.total}: {total} {currency}
                </p>
              ))}
            </Section>
          )}

          <Section title={t.detail.documents}>
            {data.documents.length === 0 && (
              <p style={{ color: "var(--text-muted)" }}>{t.noFiles}</p>
            )}
            {data.documents.map((d) => (
              <DocumentLink key={d.id} adminKey={adminKey} document={d} />
            ))}
          </Section>
        </>
      ) : (
        <p className="mt-8 text-body" style={{ color: "var(--text-muted)" }}>
          {t.detail.nothingSubmitted}
        </p>
      )}
    </main>
  );
}

function DocumentLink({
  adminKey,
  document: doc,
}: {
  adminKey: string;
  document: CustomerDetail["documents"][number];
}) {
  const t = strings.admin;
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  return (
    <p className="py-1">
      <button
        className="text-label underline"
        disabled={busy}
        onClick={() => {
          setBusy(true);
          setError(null);
          void downloadDocument(adminKey, doc.id, doc.original_filename).then(
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
        {doc.original_filename}
      </button>
      <span style={{ color: "var(--text-muted)" }}>
        {" · "}
        {doc.kind} · {Math.round(doc.size_bytes / 1024)}KB · {t.detail.download}
      </span>
      {error && (
        <span style={{ color: "var(--verdict-no)" }}>{" · "}{error}</span>
      )}
    </p>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mt-8">
      <h2 className="text-label" style={{ color: "var(--text-muted)" }}>
        {title}
      </h2>
      <div className="mt-2">{children}</div>
    </section>
  );
}

function Field({ label, value }: { label: string; value: string | null }) {
  if (!value) return null;
  return (
    <p className="py-1">
      {label && (
        <span style={{ color: "var(--text-muted)" }}>{label}: </span>
      )}
      {value}
    </p>
  );
}
