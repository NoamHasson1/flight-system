"use client";

import { useCallback, useEffect, useState } from "react";

import {
  createClaim,
  submitClaim,
  uploadDocument,
  type ClaimOut,
  type EligibilityResponse,
} from "@/lib/api";
import { strings } from "@/lib/strings";

import s from "./hero.module.css";

const t = strings.claim;

/**
 * The claim wizard.
 *
 * Five steps, because one form with thirty fields is abandoned. Steps 1-3 are
 * collected in the browser and posted as ONE request when the customer reaches
 * Documents: files need a claim_id to attach to, and the backend takes
 * passengers and expenses inline on create, so a single POST is both the
 * simplest thing and the one that cannot leave a half-built claim behind.
 *
 * Progress is mirrored to localStorage on every change. People start a claim,
 * go and find a receipt, and come back — losing their work at that moment is
 * how a claim never gets filed. The draft is dropped once it is submitted.
 */

type Passenger = { fullName: string; nationalId: string; isMinor: boolean };
type Cost = { category: string; amount: string; currency: string; description: string };

type Draft = {
  contactName: string;
  contactEmail: string;
  contactPhone: string;
  passengers: Passenger[];
  bookingReference: string;
  airlineReason: string;
  noticeDays: string;
  costs: Cost[];
};

const EMPTY_PASSENGER: Passenger = { fullName: "", nationalId: "", isMinor: false };
const EMPTY_COST: Cost = { category: "HOTEL", amount: "", currency: "EUR", description: "" };

const CATEGORIES = [
  ["HOTEL", "Hotel"],
  ["MEAL", "Food"],
  ["DRINK", "Drinks"],
  ["TRANSPORT", "Taxi or transport"],
  ["COMMUNICATION", "Phone calls"],
  ["REBOOKING", "A replacement ticket"],
  ["OTHER", "Something else"],
] as const;

const CURRENCIES = ["EUR", "GBP", "ILS", "USD"] as const;

function blankDraft(): Draft {
  return {
    contactName: "",
    contactEmail: "",
    contactPhone: "",
    passengers: [{ ...EMPTY_PASSENGER }],
    bookingReference: "",
    airlineReason: "",
    noticeDays: "",
    costs: [],
  };
}

export function ClaimWizard({ check }: { check: EligibilityResponse }) {
  const storageKey = `claim-draft:${check.check_id}`;

  const [step, setStep] = useState(0);
  const [draft, setDraft] = useState<Draft>(blankDraft);
  const [claim, setClaim] = useState<ClaimOut | null>(null);
  const [uploads, setUploads] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<ClaimOut | null>(null);

  // Restore on mount, deliberately, and NOT in a lazy useState initializer.
  //
  // react-hooks/set-state-in-effect objects to this, and in general it is
  // right: setState in an effect body causes a second render. Here the second
  // render is the point. These inputs are controlled, the page is
  // server-rendered, and localStorage does not exist on the server -- so a lazy
  // initializer would have the server emit empty fields and the client emit
  // filled ones, which is a hydration mismatch. One extra render on mount is
  // the cheaper of the two, and it only happens when there is a draft to
  // restore.
  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(storageKey);
      // eslint-disable-next-line react-hooks/set-state-in-effect -- see above
      if (saved) setDraft({ ...blankDraft(), ...JSON.parse(saved) });
    } catch {
      /* private mode, cleared storage, corrupt JSON — start fresh */
    }
  }, [storageKey]);

  useEffect(() => {
    try {
      window.localStorage.setItem(storageKey, JSON.stringify(draft));
    } catch {
      /* storage can be full or blocked; the form still works */
    }
  }, [draft, storageKey]);

  const patch = useCallback((change: Partial<Draft>) => {
    setError(null);
    setDraft((d) => ({ ...d, ...change }));
  }, []);

  // --- moving between steps ---

  async function forward() {
    setError(null);

    if (step === 0) {
      if (!draft.contactName.trim()) return setError(t.errors.needContactName);
      if (!draft.contactEmail.trim()) return setError(t.errors.needContactEmail);
      const named = draft.passengers.filter((p) => p.fullName.trim());
      if (!named.length) return setError(t.errors.needPassenger);
      patch({ passengers: named });
      return setStep(1);
    }

    if (step === 1) return setStep(2);

    if (step === 2) {
      const bad = draft.costs.find((c) => !isAmount(c.amount));
      if (bad) return setError(t.errors.badAmount);
      // Entering Documents needs a claim to attach them to.
      return void (await create());
    }

    if (step === 3) return setStep(4);
  }

  async function create() {
    if (claim) return setStep(3); // already created; do not make a second one
    setBusy(true);
    const result = await createClaim({
      check_id: check.check_id,
      contact_name: draft.contactName.trim(),
      contact_email: draft.contactEmail.trim(),
      contact_phone: draft.contactPhone.trim() || null,
      booking_reference: draft.bookingReference.trim() || null,
      airline_reason: draft.airlineReason.trim() || null,
      cancellation_notice_days: draft.noticeDays ? Number(draft.noticeDays) : null,
      passengers: draft.passengers.map((p) => ({
        full_name: p.fullName.trim(),
        national_id: p.nationalId.trim() || null,
        is_minor: p.isMinor,
      })),
      expenses: draft.costs.map((c) => ({
        category: c.category as never,
        amount: c.amount.trim(),
        currency: c.currency,
        description: c.description.trim() || null,
        incurred_on: null,
      })),
      notes: null,
    });
    setBusy(false);

    if (!result.ok) return setError(failureText(result.failure));
    setClaim(result.data);
    setStep(3);
  }

  async function attach(file: File, kind: string) {
    if (!claim) return;
    setBusy(true);
    const result = await uploadDocument(claim.id, file, kind);
    setBusy(false);
    if (!result.ok) return setError(failureText(result.failure));
    setUploads((u) => [...u, result.data.document.original_filename]);
  }

  async function finish() {
    if (!claim) return;
    setBusy(true);
    const result = await submitClaim(claim.id);
    setBusy(false);
    if (!result.ok) return setError(failureText(result.failure));
    try {
      window.localStorage.removeItem(storageKey);
    } catch {
      /* nothing to clean up */
    }
    setDone(result.data);
  }

  if (done) return <Done claim={done} />;

  return (
    <div>
      <Progress step={step} />

      <div className={`${s.panel} mt-6 p-6 sm:p-8`}>
        {step === 0 && <Passengers draft={draft} patch={patch} />}
        {step === 1 && <Booking draft={draft} patch={patch} />}
        {step === 2 && <Costs draft={draft} patch={patch} />}
        {step === 3 && (
          <Documents uploads={uploads} busy={busy} onPick={attach} />
        )}
        {step === 4 && <Review draft={draft} claim={claim} uploads={uploads} />}

        {error ? (
          <p role="alert" className={`${s.errorBox} mt-6 px-4 py-3 text-callout`}>
            {error}
          </p>
        ) : null}

        <div className="mt-8 flex items-center justify-between gap-4">
          {step > 0 && step < 4 ? (
            <button
              type="button"
              onClick={() => setStep((n) => n - 1)}
              className={`${s.secondary} px-5 py-3 text-callout`}
            >
              {t.back}
            </button>
          ) : (
            <span />
          )}

          {step < 4 ? (
            <button
              type="button"
              disabled={busy}
              onClick={() => void forward()}
              className={`${s.cta} px-7 py-3.5 text-subhead`}
              style={{ fontWeight: 700 }}
            >
              {busy ? "Working…" : t.next}
            </button>
          ) : (
            <button
              type="button"
              disabled={busy}
              onClick={() => void finish()}
              className={`${s.cta} px-7 py-3.5 text-subhead`}
              style={{ fontWeight: 700 }}
            >
              {busy ? t.review.submitting : t.review.submit}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// --- steps -------------------------------------------------------------------

function Progress({ step }: { step: number }) {
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <p className="text-micro uppercase" style={{ color: "var(--color-teal-600)" }}>
          {String(step + 1).padStart(2, "0")} of{" "}
          {String(t.steps.length).padStart(2, "0")} · {t.steps[step]}
        </p>
      </div>
      <div className={`${s.progress} mt-3`}>
        {t.steps.map((label, i) => (
          <span
            key={label}
            className={`${s.pip} ${i < step ? s.pipDone : ""} ${i === step ? s.pipNow : ""}`}
          />
        ))}
      </div>
    </div>
  );
}

function Passengers({ draft, patch }: StepProps) {
  const set = (i: number, change: Partial<Passenger>) =>
    patch({
      passengers: draft.passengers.map((p, n) => (n === i ? { ...p, ...change } : p)),
    });

  return (
    <>
      <Head title={t.passengers.title} body={t.passengers.body} />

      <div className="mt-6 grid gap-4 sm:grid-cols-2">
        <Text
          label={t.passengers.contactName}
          value={draft.contactName}
          onChange={(v) => patch({ contactName: v })}
        />
        <Text
          label={t.passengers.contactEmail}
          hint={t.passengers.contactEmailHint}
          type="email"
          value={draft.contactEmail}
          onChange={(v) => patch({ contactEmail: v })}
        />
      </div>

      <div className="mt-8 flex flex-col gap-4">
        {draft.passengers.map((p, i) => (
          <div key={i} className={`${s.row} p-4 sm:p-5`}>
            <div className="flex items-center justify-between">
              <p className="text-micro uppercase" style={{ color: "var(--text-muted)" }}>
                Passenger {i + 1}
              </p>
              {draft.passengers.length > 1 ? (
                <button
                  type="button"
                  className={`${s.removeButton} text-caption`}
                  onClick={() =>
                    patch({ passengers: draft.passengers.filter((_, n) => n !== i) })
                  }
                >
                  {t.passengers.remove}
                </button>
              ) : null}
            </div>

            <div className="mt-3 grid gap-4 sm:grid-cols-2">
              <Text
                label={t.passengers.fullName}
                value={p.fullName}
                onChange={(v) => set(i, { fullName: v })}
              />
              <Text
                label={t.passengers.nationalId}
                hint={t.passengers.nationalIdHint}
                value={p.nationalId}
                onChange={(v) => set(i, { nationalId: v })}
              />
            </div>

            <label className="mt-3 flex items-center gap-2.5 text-callout" style={{ color: "var(--text-muted)" }}>
              <input
                type="checkbox"
                checked={p.isMinor}
                onChange={(e) => set(i, { isMinor: e.target.checked })}
                style={{ accentColor: "var(--color-teal-600)", width: 18, height: 18 }}
              />
              {t.passengers.minor}
            </label>
          </div>
        ))}
      </div>

      <button
        type="button"
        onClick={() => patch({ passengers: [...draft.passengers, { ...EMPTY_PASSENGER }] })}
        className={`${s.ghostButton} mt-4 w-full px-4 py-3.5 text-callout`}
      >
        + {t.passengers.add}
      </button>
    </>
  );
}

function Booking({ draft, patch }: StepProps) {
  return (
    <>
      <Head title={t.booking.title} body={t.booking.body} />

      <div className="mt-6 flex flex-col gap-5">
        <Text
          label={t.booking.reference}
          hint={t.booking.referenceHint}
          value={draft.bookingReference}
          uppercase
          onChange={(v) => patch({ bookingReference: v })}
        />

        <label className="block">
          <Label text={t.booking.airlineReason} />
          <textarea
            rows={3}
            value={draft.airlineReason}
            onChange={(e) => patch({ airlineReason: e.target.value })}
            placeholder="They said there was a technical fault with the aircraft."
            className={`${s.field} mt-2 w-full resize-y px-4 py-3 text-body`}
          />
          <Hint>{t.booking.airlineReasonHint}</Hint>
        </label>

        <label className="block">
          <Label text={t.booking.notice} />
          <select
            value={draft.noticeDays}
            onChange={(e) => patch({ noticeDays: e.target.value })}
            className={`${s.field} mt-2 w-full px-4 py-3.5 text-body`}
          >
            {t.booking.noticeOptions.map((o) => (
              <option key={o.label} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
      </div>
    </>
  );
}

function Costs({ draft, patch }: StepProps) {
  const set = (i: number, change: Partial<Cost>) =>
    patch({ costs: draft.costs.map((c, n) => (n === i ? { ...c, ...change } : c)) });

  return (
    <>
      <Head title={t.costs.title} body={t.costs.body} />

      {draft.costs.length === 0 ? (
        <p className="mt-6 text-callout" style={{ color: "var(--text-muted)" }}>
          {t.costs.none}
        </p>
      ) : (
        <div className="mt-6 flex flex-col gap-4">
          {draft.costs.map((c, i) => (
            <div key={i} className={`${s.row} p-4 sm:p-5`}>
              <div className="flex items-center justify-between">
                <p className="text-micro uppercase" style={{ color: "var(--text-muted)" }}>
                  Cost {i + 1}
                </p>
                <button
                  type="button"
                  className={`${s.removeButton} text-caption`}
                  onClick={() => patch({ costs: draft.costs.filter((_, n) => n !== i) })}
                >
                  {t.costs.remove}
                </button>
              </div>

              <div className="mt-3 grid gap-4 sm:grid-cols-[1.3fr_1fr_0.8fr]">
                <label className="block">
                  <Label text={t.costs.category} />
                  <select
                    value={c.category}
                    onChange={(e) => set(i, { category: e.target.value })}
                    className={`${s.field} mt-2 w-full px-3 py-3 text-callout`}
                  >
                    {CATEGORIES.map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </label>

                <Text
                  label={t.costs.amount}
                  value={c.amount}
                  placeholder="42.50"
                  onChange={(v) => set(i, { amount: v })}
                />

                <label className="block">
                  <Label text={t.costs.currency} />
                  <select
                    value={c.currency}
                    onChange={(e) => set(i, { currency: e.target.value })}
                    className={`${s.field} mt-2 w-full px-3 py-3 text-callout`}
                  >
                    {CURRENCIES.map((code) => (
                      <option key={code} value={code}>
                        {code}
                      </option>
                    ))}
                  </select>
                </label>
              </div>

              <div className="mt-3">
                <Text
                  label={t.costs.description}
                  value={c.description}
                  placeholder="One night at the airport hotel"
                  onChange={(v) => set(i, { description: v })}
                />
              </div>
            </div>
          ))}
        </div>
      )}

      <button
        type="button"
        onClick={() => patch({ costs: [...draft.costs, { ...EMPTY_COST }] })}
        className={`${s.ghostButton} mt-4 w-full px-4 py-3.5 text-callout`}
      >
        + {t.costs.add}
      </button>
    </>
  );
}

function Documents({
  uploads,
  busy,
  onPick,
}: {
  uploads: string[];
  busy: boolean;
  onPick: (file: File, kind: string) => void;
}) {
  return (
    <>
      <Head title={t.documents.title} body={t.documents.body} />

      <div className="mt-6 flex flex-col gap-4">
        {[
          [t.documents.booking, "BOOKING"],
          [t.documents.receipt, "RECEIPT"],
          [t.documents.boardingPass, "BOARDING_PASS"],
        ].map(([label, kind]) => (
          <label key={kind} className={`${s.row} flex cursor-pointer items-center justify-between gap-4 p-4 sm:p-5`}>
            <span className="text-subhead" style={{ color: "var(--text-strong)" }}>
              {label}
            </span>
            <span className={`${s.secondary} px-4 py-2.5 text-callout`}>
              {t.documents.drop}
            </span>
            <input
              type="file"
              className="sr-only"
              disabled={busy}
              accept="application/pdf,image/jpeg,image/png,image/webp,image/heic"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) onPick(file, kind);
                e.target.value = ""; // so the same file can be re-picked
              }}
            />
          </label>
        ))}
      </div>

      {uploads.length ? (
        <ul className="mt-5 flex flex-col gap-2.5">
          {uploads.map((name, i) => (
            <li key={`${name}-${i}`} className={`${s.fileChip} px-4 py-2.5 text-callout`}>
              <svg viewBox="0 0 24 24" className="size-4 shrink-0" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                <path d="M20 6 9 17l-5-5" />
              </svg>
              <span className="truncate">{name}</span>
            </li>
          ))}
        </ul>
      ) : null}

      <p className="mt-5 text-caption" style={{ color: "var(--text-muted)" }}>
        {t.documents.later}
      </p>
    </>
  );
}

function Review({
  draft,
  claim,
  uploads,
}: {
  draft: Draft;
  claim: ClaimOut | null;
  uploads: string[];
}) {
  return (
    <>
      <Head title={t.review.title} body={t.review.body} />

      <dl className="mt-6 flex flex-col gap-5">
        <Summary label={t.review.passengers}>
          {draft.passengers.map((p) => (
            <span key={p.fullName} className="block">
              {p.fullName}
              {p.nationalId ? ` · ${p.nationalId}` : ""}
              {p.isMinor ? " · under 18" : ""}
            </span>
          ))}
        </Summary>

        <Summary label={t.review.booking}>
          {draft.bookingReference || "—"}
          {draft.airlineReason ? (
            <span className="mt-1 block" style={{ color: "var(--text-muted)" }}>
              &ldquo;{draft.airlineReason}&rdquo;
            </span>
          ) : null}
        </Summary>

        <Summary label={t.review.costs}>
          {draft.costs.length
            ? draft.costs.map((c, i) => (
                <span key={i} className="tabular block">
                  {c.amount} {c.currency} · {c.category.toLowerCase()}
                  {c.description ? ` · ${c.description}` : ""}
                </span>
              ))
            : "None"}
        </Summary>

        <Summary label={t.review.documents}>
          {uploads.length ? uploads.join(", ") : "None uploaded"}
        </Summary>
      </dl>

      {claim ? (
        <p className="mt-6 text-caption" style={{ color: "var(--text-muted)" }}>
          Reference <strong className="tabular">{claim.reference}</strong>
        </p>
      ) : null}

      <p className="mt-5 text-caption" style={{ color: "var(--text-muted)" }}>
        {t.review.consent}
      </p>
    </>
  );
}

function Done({ claim }: { claim: ClaimOut }) {
  return (
    <div className={`${s.panel} p-8 text-center`}>
      <span
        className="mx-auto grid size-14 place-items-center rounded-full"
        style={{ background: "var(--verdict-yes-fill)", color: "var(--verdict-yes)" }}
        aria-hidden
      >
        <svg viewBox="0 0 24 24" className="size-7" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
          <path d="M20 6 9 17l-5-5" />
        </svg>
      </span>

      <h2 className="mt-5 text-title" style={{ color: "var(--text-strong)" }}>
        {t.done.title}
      </h2>
      <p className="mx-auto mt-3 max-w-sm text-body" style={{ color: "var(--text-muted)" }}>
        {t.done.body}
      </p>

      <p className="mt-7 text-micro uppercase" style={{ color: "var(--text-muted)" }}>
        {t.done.reference}
      </p>
      <p
        className="tabular mt-1 text-title"
        style={{ color: "var(--color-teal-600)", fontFamily: "var(--font-sans-stack)" }}
      >
        {claim.reference}
      </p>
    </div>
  );
}

// --- bits --------------------------------------------------------------------

type StepProps = { draft: Draft; patch: (change: Partial<Draft>) => void };

function Head({ title, body }: { title: string; body: string }) {
  return (
    <>
      <h2 className="text-heading" style={{ color: "var(--text-strong)" }}>
        {title}
      </h2>
      <p className="mt-2 max-w-prose text-callout" style={{ color: "var(--text-muted)" }}>
        {body}
      </p>
    </>
  );
}

/**
 * The label only. The hint goes BELOW the input, never between the two.
 *
 * A hint between label and input pushes that input down, so two fields side by
 * side in a grid stop lining up the moment one of them has a hint — which
 * looks like a bug and reads as carelessness. Under the input it also arrives
 * when it is actually useful: after you have seen the field.
 */
function Label({ text }: { text: string }) {
  return (
    <span className="text-micro uppercase" style={{ color: "var(--text-muted)" }}>
      {text}
    </span>
  );
}

function Hint({ children }: { children?: string }) {
  if (!children) return null;
  return (
    <span className="mt-1.5 block text-caption" style={{ color: "var(--text-muted)" }}>
      {children}
    </span>
  );
}

function Text({
  label,
  hint,
  value,
  onChange,
  placeholder,
  type = "text",
  uppercase,
}: {
  label: string;
  hint?: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  type?: string;
  uppercase?: boolean;
}) {
  return (
    <label className="block">
      <Label text={label} />
      <input
        type={type}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className={`${s.field} mt-2 w-full px-4 py-3.5 text-body ${uppercase ? "uppercase tabular" : ""}`}
      />
      <Hint>{hint}</Hint>
    </label>
  );
}

function Summary({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-micro uppercase" style={{ color: "var(--text-muted)" }}>
        {label}
      </dt>
      <dd className="mt-1.5 text-body" style={{ color: "var(--text-strong)" }}>
        {children}
      </dd>
    </div>
  );
}

function isAmount(value: string): boolean {
  return /^\d+(\.\d{1,2})?$/.test(value.trim()) && Number(value) > 0;
}

function failureText(failure: { kind: string; message?: string; messages?: string[] }): string {
  if (failure.kind === "refused" && failure.message) return failure.message;
  if (failure.kind === "invalid" && failure.messages?.length)
    return failure.messages.join(" ");
  return strings.errors.unreachable;
}
