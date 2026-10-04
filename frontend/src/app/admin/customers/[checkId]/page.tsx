/**
 * One customer, everything they submitted, on its own URL.
 *
 * WHY A PAGE AND NOT THE SLIDE-OVER
 *
 * The panel was built for "open one, glance, close, open the next" and it
 * is still right for that. This is the other job: an operator with the
 * airline's form open in one tab and the customer in another, copying
 * fields across. That wants a real address -- something you can open in a
 * new tab, keep open, bookmark, and paste to a colleague.
 *
 * So the row now opens this in a NEW TAB and the panel is gone. Two ways
 * to see the same thing is two things to keep in step.
 *
 * ORGANISED BY HEADING, AND THE HEADINGS ARE THE POINT. An operator
 * transcribing a claim is looking for one field at a time; a wall of
 * label-value pairs makes them read the whole thing to find the one.
 */

"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";

import { readCustomer, type CustomerDetail } from "@/lib/api";
import { useAdminKey } from "@/lib/session-key";
import { strings } from "@/lib/strings";
import { Files } from "../../Files";
import { Toast, useToast } from "../../Toast";
import { Outreach } from "./Outreach";
import s from "../../crm.module.css";

export default function CustomerPage({
  params,
}: {
  params: Promise<{ checkId: string }>;
}) {
  const { checkId } = use(params);
  const [key] = useAdminKey();
  const t = strings.admin;

  if (key === null) {
    return (
      <main className={s.gate}>
        <div className={s.gateCard}>
          <h1 className={s.gateTitle}>{t.detail.title}</h1>
          <p className={s.gateText}>{t.keyExplain}</p>
          <Link
            href="/admin"
            className={s.primary}
            style={{ display: "block", textAlign: "center", textDecoration: "none" }}
          >
            {t.enter}
          </Link>
        </div>
      </main>
    );
  }
  return <Customer adminKey={key} checkId={checkId} />;
}

function Customer({ adminKey, checkId }: { adminKey: string; checkId: string }) {
  const t = strings.admin;
  const [data, setData] = useState<CustomerDetail | null>(null);
  const [failed, setFailed] = useState<"denied" | "unreachable" | null>(null);
  /**
   * Bumped to re-read after sending something.
   *
   * A counter rather than calling a `load()` function from the handler.
   * The fetch then lives in exactly one place, which is the only way the
   * `alive` guard below can cover every path -- a second call site is a
   * second chance to set state on a page somebody has already left.
   */
  const [reloads, setReloads] = useState(0);
  const toast = useToast();

  useEffect(() => {
    let alive = true;
    void readCustomer(adminKey, checkId).then((r) => {
      // The operator may have closed the tab while this was in flight.
      if (!alive) return;
      if (r.ok) setData(r.data);
      else setFailed(r.failure.kind === "denied" ? "denied" : "unreachable");
    });
    return () => {
      alive = false;
    };
  }, [adminKey, checkId, reloads]);

  if (failed) {
    return (
      <main className={s.sheet} style={{ paddingTop: "3rem" }}>
        <p className={s.empty}>
          {failed === "denied" ? t.flights.denied : t.failed}
        </p>
      </main>
    );
  }
  if (!data) {
    return (
      <main className={s.sheet} style={{ paddingTop: "3rem" }}>
        <div className={s.skeleton} style={{ height: "2rem", width: "40%" }} />
      </main>
    );
  }

  return (
    <div className={s.desk}>
      {/* Not part of the document, and it does not print. */}
      <div className={`${s.docBar} ${s.noPrint}`}>
        <Link href="/admin" className={s.ghost} style={{ textDecoration: "none" }}>
          ← {t.customersBack}
        </Link>
        <span className={s.spacer} />
        <CopyEverything data={data} onCopied={() => toast.show({ text: t.copy.done })} />
        <button type="button" className={s.ghost} onClick={() => window.print()}>
          {t.copy.print}
        </button>
      </div>

      <main className={s.sheet2}>
        <header className={s.docHead}>
          <h1 className={s.docTitle}>{data.contact_name || "—"}</h1>
          <p className={s.docSub}>
            <span className={s.num}>{data.flight_number}</span>
            <span aria-hidden>·</span>
            <span className={s.num}>{data.flight_date}</span>
            {data.verdict && (
              <span className={`${s.pill} ${verdictTone(data.verdict)}`}>
                {t.verdicts[data.verdict] ?? data.verdict}
              </span>
            )}
            {data.best_amount && (
              <span className={s.amount}>
                {money(data.best_amount, data.best_currency)}
              </span>
            )}
          </p>
        </header>

        <Section title={t.detail.contact}>
          <Fields
            rows={[
              [t.columns.email, data.contact_email],
              [t.columns.phone, data.contact_phone],
            ]}
          />
        </Section>

        {data.claim_id ? (
          <>
            <Section title={t.detail.claim}>
              <Fields
                rows={[
                  [t.detail.reference, data.claim_reference],
                  [t.detail.bookingReference, data.booking_reference],
                  [t.detail.airlineReason, data.airline_reason],
                  [
                    t.detail.cancellationNotice,
                    data.cancellation_notice
                      ? (t.notice[data.cancellation_notice] ?? data.cancellation_notice)
                      : null,
                  ],
                  [
                    t.detail.state,
                    data.claim_submitted_at ? t.detail.submitted : t.detail.notSubmitted,
                  ],
                ]}
              />
            </Section>

            {data.passengers.length > 0 && (
              <Section title={`${t.detail.passengers} (${data.passengers.length})`}>
                {data.passengers.map((p, i) => (
                  <div key={i} className={s.docRow}>
                    <strong>{p.full_name}</strong>
                    {p.national_id && (
                      <span className={s.muted}>
                        {t.detail.nationalId} <span className={s.num}>{p.national_id}</span>
                      </span>
                    )}
                    {p.is_minor && <span className={s.muted}>{t.detail.minor}</span>}
                  </div>
                ))}
              </Section>
            )}

            {data.expenses.length > 0 && (
              <Section title={t.detail.expenses}>
                {data.expenses.map((e) => (
                  <div key={e.id} className={s.docRow}>
                    <span className={s.amount}>{money(e.amount, e.currency)}</span>
                    <span>{t.categories[e.category] ?? e.category}</span>
                    {e.description && <span className={s.muted}>{e.description}</span>}
                  </div>
                ))}
                {Object.entries(data.expense_totals).map(([currency, sum]) => (
                  <p key={currency} className={s.docTotal}>
                    {t.detail.total} {money(sum, currency)}
                  </p>
                ))}
              </Section>
            )}

            <Section title={`${t.detail.documents} (${data.documents.length})`}>
              {data.documents.length === 0 ? (
                <p className={s.note}>{t.noFiles}</p>
              ) : (
                <Files adminKey={adminKey} documents={data.documents} />
              )}
            </Section>

            <Outreach
              adminKey={adminKey}
              claimId={data.claim_id}
              onDone={(text) => {
                toast.show({ text });
                setReloads((n) => n + 1);
              }}
            />
          </>
        ) : (
          <Section title={t.detail.claim}>
            <p className={s.note}>{t.detail.nothingSubmitted}</p>
          </Section>
        )}
      </main>

      <Toast message={toast.message} onDismiss={toast.dismiss} />
    </div>
  );
}

/**
 * Copy the whole record, as text, in one press.
 *
 * WHAT IT COPIES AND WHY IT IS NOT JSON
 *
 * The destination is an airline's web form or a letter, not another
 * program. Labelled lines paste into both and can be read by the person
 * pasting them; JSON would have to be translated by hand at the other
 * end, which is the work this is meant to remove.
 *
 * Files are listed by name and kind rather than attached -- a clipboard
 * cannot carry them, and a list that says what exists is more honest than
 * silence about it.
 */
function CopyEverything({
  data,
  onCopied,
}: {
  data: CustomerDetail;
  onCopied: () => void;
}) {
  const t = strings.admin;
  const [done, setDone] = useState(false);

  return (
    <button
      type="button"
      className={s.copyAll}
      onClick={() => {
        void navigator.clipboard?.writeText(asText(data)).then(() => {
          setDone(true);
          onCopied();
          // Back to the idle label, so the button does not claim
          // "copied" about a press that happened five minutes ago.
          setTimeout(() => setDone(false), 2000);
        }, () => {});
      }}
    >
      <CopyIcon />
      {done ? t.copy.done : t.copy.all}
    </button>
  );
}

function asText(d: CustomerDetail): string {
  const t = strings.admin;
  const out: string[] = [];
  const line = (label: string, value: unknown) => {
    if (value === null || value === undefined || value === "") return;
    out.push(`${label}: ${value}`);
  };

  out.push(`${t.detail.title} — ${d.contact_name ?? ""}`);
  out.push("");
  out.push(`[${t.flightHeading}]`);
  line(t.columns.flight, d.flight_number);
  line(t.columns.date, d.flight_date);
  line(t.columns.verdict, d.verdict ? (t.verdicts[d.verdict] ?? d.verdict) : null);
  line(
    t.columns.amount,
    d.best_amount ? money(d.best_amount, d.best_currency) : null,
  );

  out.push("");
  out.push(`[${t.detail.contact}]`);
  line(t.columns.customer, d.contact_name);
  line(t.columns.email, d.contact_email);
  line(t.columns.phone, d.contact_phone);

  if (d.claim_id) {
    out.push("");
    out.push(`[${t.detail.claim}]`);
    line(t.detail.reference, d.claim_reference);
    line(t.detail.bookingReference, d.booking_reference);
    line(t.detail.airlineReason, d.airline_reason);
    line(
      t.detail.cancellationNotice,
      d.cancellation_notice
        ? (t.notice[d.cancellation_notice] ?? d.cancellation_notice)
        : null,
    );

    if (d.passengers.length) {
      out.push("");
      out.push(`[${t.detail.passengers}]`);
      for (const p of d.passengers) {
        out.push(
          `${p.full_name}${p.national_id ? ` · ${t.detail.nationalId} ${p.national_id}` : ""}` +
            `${p.is_minor ? ` · ${t.detail.minor}` : ""}`,
        );
      }
    }

    if (d.expenses.length) {
      out.push("");
      out.push(`[${t.detail.expenses}]`);
      for (const e of d.expenses) {
        out.push(
          `${money(e.amount, e.currency)} · ${t.categories[e.category] ?? e.category}` +
            `${e.description ? ` · ${e.description}` : ""}`,
        );
      }
      for (const [currency, sum] of Object.entries(d.expense_totals)) {
        out.push(`${t.detail.total} ${money(sum, currency)}`);
      }
    }

    out.push("");
    out.push(`[${t.detail.documents}]`);
    if (!d.documents.length) {
      out.push(t.noFiles);
    } else {
      for (const f of d.documents) {
        out.push(
          `${f.original_filename} · ${t.kinds[f.kind] ?? f.kind} · ` +
            `${Math.max(1, Math.round(f.size_bytes / 1024))}KB`,
        );
      }
    }
  }

  return out.join("\n");
}

function verdictTone(verdict: string): string {
  if (verdict === "ELIGIBLE" || verdict === "LIKELY_ELIGIBLE") return s.pillYes;
  if (verdict === "NEEDS_REVIEW") return s.pillReview;
  return s.pillNo;
}

const SYMBOL: Record<string, string> = { EUR: "€", GBP: "£", ILS: "₪" };

function money(amount: string, currency: string | null): string {
  const symbol = currency ? (SYMBOL[currency] ?? `${currency} `) : "";
  return `${symbol}${Number(amount).toLocaleString("he-IL", {
    minimumFractionDigits: 2,
  })}`;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className={s.docSection}>
      <h2 className={s.docSectionTitle}>{title}</h2>
      {children}
    </section>
  );
}

function Fields({ rows }: { rows: Array<[string, string | null]> }) {
  const present = rows.filter(([, value]) => value);
  if (!present.length) return null;
  return (
    <dl className={s.docFields}>
      {present.map(([label, value]) => (
        <Row key={label} label={label} value={value as string} />
      ))}
    </dl>
  );
}

/** Each value copies itself. The whole-record button is for the whole
    record; most of the time an operator wants one field. */
function Row({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className={s.docLabel}>{label}</dt>
      <dd className={s.docValue}>
        <button
          type="button"
          className={s.copy}
          title={value}
          onClick={() => void navigator.clipboard?.writeText(value).catch(() => {})}
        >
          {value}
        </button>
      </dd>
    </div>
  );
}

/** Two offset rounded squares -- the copy glyph everybody already knows.
 *
 *  NOT exported. A Next page file may only export a fixed set of names
 *  (`default`, `metadata`, `dynamic`, and friends), and anything else
 *  fails type-checking with a message about an index signature that says
 *  nothing about the real problem. Turbopack's build does not run that
 *  check; webpack's does, which is how this was found.
 */
function CopyIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden>
      <rect x="5.4" y="5.4" width="8.2" height="8.2" rx="2"
        stroke="currentColor" strokeWidth="1.4" />
      <path d="M10.6 3.2A2 2 0 0 0 8.8 2.4H4.4a2 2 0 0 0-2 2v4.4a2 2 0 0 0 .8 1.6"
        stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  );
}
