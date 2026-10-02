"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";

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
type Cost = {
  category: string;
  amount: string;
  currency: string;
  description: string;
  /**
   * The receipt proving this expense, held until the claim exists.
   *
   * A File, not an uploaded id: documents attach to a claim, and the
   * claim is not created until the costs step is submitted. These go up
   * immediately afterwards, each tagged with its expense's id.
   */
  receipt: File | null;
};

type Draft = {
  contactName: string;
  contactEmail: string;
  contactPhone: string;
  passengers: Passenger[];
  bookingReference: string;
  airlineReason: string;
  cancellationNotice: string;
  alreadyGot: string;
  anythingElse: string;
  costs: Cost[];
};

const EMPTY_PASSENGER: Passenger = { fullName: "", nationalId: "", isMinor: false };
const EMPTY_COST: Cost = {
  category: "HOTEL",
  amount: "",
  currency: "EUR",
  description: "",
  receipt: null,
};

const CATEGORIES = [
  ["HOTEL", "מלון"],
  ["MEAL", "אוכל"],
  ["DRINK", "שתייה"],
  ["TRANSPORT", "מונית או תחבורה"],
  ["COMMUNICATION", "שיחות טלפון"],
  ["REBOOKING", "כרטיס חלופי"],
  ["OTHER", "משהו אחר"],
] as const;

const CURRENCIES = ["EUR", "GBP", "ILS", "USD"] as const;

/**
 * A fresh draft, with as many passenger rows as the result screen was told.
 *
 * The counter on the verdict page is not decoration: it changes the amount
 * shown there, and somebody who said "four of us" has already answered this
 * question. Asking again three screens later is how a form starts to feel
 * like paperwork -- and worse, it invites a different answer, which then
 * disagrees with the figure that persuaded them to start.
 *
 * Clamped, because the count arrives in a URL and a URL is typed by anyone.
 */
function blankDraft(passengers = 1): Draft {
  const rows = Math.min(Math.max(Math.trunc(passengers) || 1, 1), 9);
  return {
    contactName: "",
    contactEmail: "",
    contactPhone: "",
    alreadyGot: "NOTHING",
    anythingElse: "",
    passengers: Array.from({ length: rows }, () => ({ ...EMPTY_PASSENGER })),
    bookingReference: "",
    airlineReason: "",
    cancellationNotice: "",
    costs: [],
  };
}

/**
 * Mirrors `BOOKING_REFERENCE_MAX` in app/schemas/claims.py.
 *
 * Duplicated deliberately rather than generated: it is one integer, and the
 * alternative is a build step for a number that changes once a decade. The
 * API types are generated from OpenAPI, which does carry the constraint, so
 * a mismatch is caught the moment anyone regenerates them -- and the server
 * is still the authority either way. This copy exists so the customer finds
 * out while typing instead of three steps later.
 */
const BOOKING_REFERENCE_MAX = 64;

/**
 * Deliberately loose. The server is the authority on what it will accept,
 * and the only job here is to catch the obvious slip -- a missing @, a
 * missing dot -- at the moment the person can still see the field.
 *
 * A strict pattern would be worse than none: every regex that tries to
 * implement RFC 5322 rejects somebody's real address, and being told
 * "that is not an email" about an address you have used for ten years is
 * a far worse experience than a server round trip.
 */
const LOOKS_LIKE_EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function ClaimWizard({ check }: { check: EligibilityResponse }) {
  const storageKey = `claim-draft:${check.check_id}`;

  const [step, setStep] = useState(0);
  // Read once, at mount. `useSearchParams` would make this a client route
  // that re-renders on every navigation for a value that cannot change.
  const [draft, setDraft] = useState<Draft>(() =>
    blankDraft(
      typeof window === "undefined"
        ? 1
        : Number(new URLSearchParams(window.location.search).get("passengers")),
    ),
  );
  const [claim, setClaim] = useState<ClaimOut | null>(null);
  const [uploads, setUploads] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<ClaimOut | null>(null);
  const headingRef = useRef<HTMLDivElement>(null);
  const errorRef = useRef<HTMLParagraphElement>(null);

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

  /**
   * On every step change: scroll to the top and move focus to the new heading.
   *
   * Without this the browser keeps both the scroll position and the focus
   * where they were, so on a phone tapping Continue appears to do nothing --
   * the next step rendered, but you are still looking at the bottom of it. And
   * a screen reader announces nothing at all, because as far as it is
   * concerned the page did not change.
   *
   * `behavior: "auto"` rather than "smooth": this is a page change, not a
   * gesture, and smooth-scrolling a page change fights anyone using reduced
   * motion.
   */
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "auto" });
    headingRef.current?.focus();
  }, [step, done]);

  /** Validation failures move focus to the message, so it is not missed. */
  useEffect(() => {
    if (error) errorRef.current?.focus();
  }, [error]);

  const patch = useCallback((change: Partial<Draft>) => {
    setError(null);
    setDraft((d) => ({ ...d, ...change }));
  }, []);

  // --- moving between steps ---

  async function forward() {
    setError(null);

    // Step 0 asks only for a way to reach somebody. Deliberately the
    // cheapest step in the form: if they stop here we can still write to
    // them, which is not true of any later abandonment.
    if (step === 0) {
      if (!draft.contactName.trim()) return setError(t.errors.needContactName);
      if (!draft.contactEmail.trim()) return setError(t.errors.needContactEmail);
      // CHECKED HERE, where the address is typed.
      //
      // The claim is only created at the end of the costs step, so an
      // address the server rejected surfaced two steps later -- as raw
      // English from Pydantic, on a page about hotel bills, about a field
      // the customer could no longer see. They had filled in passengers
      // and receipts before learning they had mistyped their own email.
      if (!LOOKS_LIKE_EMAIL.test(draft.contactEmail.trim())) {
        return setError(strings.errors.emailFormat);
      }
      return setStep(1);
    }

    if (step === 1) {
      const named = draft.passengers.filter((p) => p.fullName.trim());
      if (!named.length) return setError(t.errors.needPassenger);
      // Checked HERE, where it is typed, not at submit.
      //
      // The claim is only created at the end of the costs step, so a server
      // rejection about this field used to surface two steps later, after
      // the passengers and every receipt had been entered. The customer saw
      // an English sentence with no field name and no way back to the thing
      // that caused it.
      if (draft.bookingReference.trim().length > BOOKING_REFERENCE_MAX) {
        return setError(
          strings.errors.tooLong(
            strings.errors.fieldNames.booking_reference,
            BOOKING_REFERENCE_MAX,
          ),
        );
      }
      patch({ passengers: named });
      return setStep(2);
    }

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
      cancellation_notice: (draft.cancellationNotice || null) as never,
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

    /**
     * Now that the expenses have ids, send up the receipts attached to
     * them.
     *
     * Paired BY POSITION: the server creates expenses in the order they
     * were sent, so the nth returned expense is the nth cost on the form.
     * That is a real assumption, which is why the length is checked
     * rather than trusted -- a mismatch means something changed on the
     * server and the right answer is to upload nothing rather than file
     * somebody's hotel receipt against their taxi.
     *
     * A failed upload does NOT block the claim. The claim is the valuable
     * thing and it is already saved; a receipt can be added from the
     * documents step or the link we email. Losing the claim because a
     * photo would not upload would be the worse trade by a long way.
     */
    const expenses = result.data.expenses;
    if (expenses.length === draft.costs.length) {
      for (const [i, cost] of draft.costs.entries()) {
        if (!cost.receipt) continue;
        const sent = await uploadDocument(
          result.data.id,
          cost.receipt,
          "RECEIPT",
          expenses[i].id,
        );
        if (sent.ok) {
          setUploads((u) => [...u, sent.data.document.original_filename]);
        }
      }
    }

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

      {/*
        A form element, so Enter submits the step rather than doing nothing.
        Pressing Enter in a text field is what people do, and a wizard that
        ignores it feels broken in a way nobody reports.
      */}
      <form
        className={`${s.panel} mt-6 p-6 sm:p-8`}
        onSubmit={(event) => {
          event.preventDefault();
          if (step < 4) void forward();
          else void finish();
        }}
      >
        {/* tabIndex -1 so focus can be moved here programmatically without
            putting it in the tab order. */}
        <div ref={headingRef} tabIndex={-1} style={{ outline: "none" }}>
          {step === 0 && <Contact draft={draft} patch={patch} />}
          {step === 1 && <Passengers draft={draft} patch={patch} />}
          {step === 2 && <Costs draft={draft} patch={patch} />}
          {step === 3 && (
            <Documents uploads={uploads} busy={busy} onPick={attach} />
          )}
          {step === 4 && (
            <Review draft={draft} claim={claim} uploads={uploads} check={check} />
          )}
        </div>

        {/* aria-live so the message is announced when it appears, not only
            when focus happens to land on it. */}
        <p
          ref={errorRef}
          tabIndex={-1}
          role="alert"
          aria-live="polite"
          className={error ? `${s.errorBox} mt-6 px-4 py-3 text-callout` : "sr-only"}
        >
          {error ?? ""}
        </p>

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
              type="submit"
              disabled={busy}
              className={`${s.cta} px-7 py-3.5 text-subhead`}
              style={{ fontWeight: 700 }}
            >
              {busy ? "רגע…" : t.next}
            </button>
          ) : (
            <button
              type="submit"
              disabled={busy}
              className={`${s.cta} px-7 py-3.5 text-subhead`}
              style={{ fontWeight: 700 }}
            >
              {busy ? t.review.submitting : t.review.submit}
            </button>
          )}
        </div>
      </form>
    </div>
  );
}

// --- steps -------------------------------------------------------------------

function Progress({ step }: { step: number }) {
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <p className="text-micro uppercase" style={{ color: "var(--color-teal-600)" }}>
          {step + 1} מתוך {t.steps.length} · {t.steps[step]}
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

/**
 * Step one: who to reply to, and what happened.
 *
 * Everything here arrives in about thirty seconds, which is the point. The
 * old form asked for every passenger's identity number first -- the slowest
 * possible opening, demanded of somebody who has not yet committed to
 * anything, and it meant an abandoned form left no way at all to reach them.
 */
function Contact({ draft, patch }: StepProps) {
  const c = t.contact;
  return (
    <>
      <Head title={c.title} body={c.body} />

      <div className="mt-6 flex flex-col gap-5">
        <Text
          label={c.phone}
          hint={c.phoneHint}
          type="tel"
          value={draft.contactPhone}
          onChange={(v) => patch({ contactPhone: v })}
        />

        <div className="grid gap-5 sm:grid-cols-2">
          <Text
            label={c.name}
            value={draft.contactName}
            onChange={(v) => patch({ contactName: v })}
          />
          <Text
            label={c.email}
            type="email"
            value={draft.contactEmail}
            onChange={(v) => patch({ contactEmail: v })}
          />
        </div>

        {/* REMOVED: "what did the airline already give you" and "what
            happened on the flight".
            
            Both were real questions that change how a letter is written,
            and both were asked of somebody who has just been told they
            are owed money and wants to get on with it. They are better
            asked later, by a person, once the claim exists -- so the form
            collects what only the customer can give us and nothing else.
            The columns stay in the database and the admin screen still
            shows them. */}

      </div>

      <p className="mt-6 text-center text-caption" style={{ color: "var(--text-muted)" }}>
        {c.nextUp}
      </p>
    </>
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

      {/* PNR first: one field, shared by everybody on the booking, and the
          thing an airline matches a claim against. */}
      <div className="mt-6">
        <Text
          label={t.passengers.reference}
          hint={t.passengers.referenceHint}
          value={draft.bookingReference}
          uppercase
          onChange={(v) => patch({ bookingReference: v })}
        />
      </div>

      <div className="mt-8 flex flex-col gap-4">
        {draft.passengers.map((p, i) => (
          <div key={i} className={`${s.row} p-4 sm:p-5`}>
            <div className="flex items-center justify-between">
              <p className="text-micro uppercase" style={{ color: "var(--text-muted)" }}>
                נוסע {i + 1}
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
      <div className="mt-6">
        <Field label={t.passengers.anythingElse} hint={t.passengers.anythingElseHint}>
          {(id, describedBy) => (
            <textarea
              id={id}
              rows={3}
              aria-describedby={describedBy}
              value={draft.anythingElse}
              onChange={(e) => patch({ anythingElse: e.target.value })}
              placeholder="תארו במילים שלכם מה קרה, פרטים נוספים על השיבוש, הוצאות, וכו׳"
              className={`${s.field} mt-2 w-full resize-y px-4 py-3 text-body`}
            />
          )}
        </Field>
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
                <Field label={t.costs.category}>
                  {(id) => (
                    <select
                      id={id}
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
                  )}
                </Field>

                <Text
                  label={t.costs.amount}
                  value={c.amount}
                  placeholder="42.50"
                  onChange={(v) => set(i, { amount: v })}
                />

                <Field label={t.costs.currency}>
                  {(id) => (
                    <select
                      id={id}
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
                  )}
                </Field>
              </div>

              <div className="mt-3">
                <Text
                  label={t.costs.description}
                  value={c.description}
                  placeholder="לילה אחד במלון בשדה התעופה"
                  onChange={(v) => set(i, { description: v })}
                />
              </div>

              {/* The receipt, on the expense it proves.
              
                  Held in memory rather than uploaded now: a document has
                  to attach to a claim, and the claim does not exist until
                  this step is submitted. The files go up immediately
                  afterwards, each tagged with the id of the expense it
                  belongs to. */}
              <div className="mt-3">
                <p className={`${s.label} text-caption`}>{t.costs.receipt}</p>
                <div className="mt-2 flex flex-wrap items-center gap-3">
                  <label className={`${s.ghostButton} cursor-pointer px-4 py-2 text-caption`}>
                    {c.receipt ? t.costs.receiptChosen : t.costs.receiptChoose}
                    <input
                      type="file"
                      accept="image/*,application/pdf"
                      className="sr-only"
                      onChange={(e) =>
                        set(i, { receipt: e.target.files?.[0] ?? null })
                      }
                    />
                  </label>
                  {c.receipt && (
                    <>
                      <span className="text-caption" style={{ color: "var(--text-strong)" }}>
                        {c.receipt.name}
                      </span>
                      <button
                        type="button"
                        className={`${s.removeButton} text-caption`}
                        onClick={() => set(i, { receipt: null })}
                      >
                        {t.costs.receiptRemove}
                      </button>
                    </>
                  )}
                </div>
                <p className="mt-1 text-caption" style={{ color: "var(--text-muted)" }}>
                  {t.costs.receiptHint}
                </p>
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
        {/* RECEIPTS ARE NOT HERE ANY MORE. They are attached to the
            expense they prove, on the costs step, so that neither the
            customer nor we have to work out afterwards which receipt
            belongs to which charge. */}
        {[
          [t.documents.booking, "BOOKING"],
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
  check,
}: {
  draft: Draft;
  claim: ClaimOut | null;
  uploads: string[];
  check: EligibilityResponse;
}) {
  /**
   * WHAT A LAST SCREEN IS FOR.
   *
   * The previous version listed bare values under one-word labels: "—"
   * for an empty booking reference, "EUR · drink 50" for an expense, and
   * no mention anywhere of the flight or the amount being claimed. It
   * answered "what did I type" when the only question that matters here
   * is "is this right, and is it worth pressing the button".
   *
   * So it now leads with the flight and the money, says what each line
   * means, and spells out the empty cases instead of printing a dash.
   */
  const totals = new Map<string, number>();
  for (const c of draft.costs) {
    const amount = Number(c.amount);
    if (!Number.isFinite(amount)) continue;
    totals.set(c.currency, (totals.get(c.currency) ?? 0) + amount);
  }

  const categoryName = (code: string) =>
    CATEGORIES.find(([value]) => value === code)?.[1] ?? code;

  return (
    <>
      <Head title={t.review.title} body={t.review.body} />

      <dl className="mt-6 flex flex-col gap-5">
        <Summary label={t.review.flight}>
          <span className="tabular">
            {check.flight?.flight_number} · {check.flight?.flight_date}
          </span>
          {check.flight?.route ? (
            <span className="mt-1 block tabular" style={{ color: "var(--text-muted)" }}>
              {check.flight.route}
            </span>
          ) : null}
        </Summary>

        {/* The number, because it is the reason anybody is on this screen
            and it was nowhere on it. */}
        {check.best_award ? (
          <Summary label={t.review.worth}>
            <span
              className="tabular text-subhead"
              style={{ color: "var(--verdict-yes)", fontWeight: 700 }}
            >
              {check.best_award.formatted}
            </span>
            <span className="mt-1 block" style={{ color: "var(--text-muted)" }}>
              {t.review.perPassenger}
            </span>
          </Summary>
        ) : null}

        <Summary label={t.review.contact}>
          {draft.contactName}
          <span className="mt-1 block" style={{ color: "var(--text-muted)" }}>
            {draft.contactEmail}
            {draft.contactPhone ? ` · ${draft.contactPhone}` : ""}
          </span>
        </Summary>

        <Summary label={t.review.passengers}>
          {draft.passengers.map((p) => (
            <span key={p.fullName} className="block">
              {p.fullName}
              {p.nationalId ? ` · ${p.nationalId}` : ""}
              {p.isMinor ? " · קטין" : ""}
            </span>
          ))}
        </Summary>

        <Summary label={t.review.booking}>
          {draft.bookingReference || (
            <span style={{ color: "var(--text-muted)" }}>
              {t.review.bookingMissing}
            </span>
          )}
        </Summary>

        <Summary label={t.review.costs}>
          {draft.costs.length === 0 ? (
            <span style={{ color: "var(--text-muted)" }}>{t.review.costsNone}</span>
          ) : (
            <>
              {draft.costs.map((c, i) => (
                <span key={i} className="block">
                  <span className="tabular">
                    {c.amount} {c.currency}
                  </span>{" "}
                  · {categoryName(c.category)}
                  {c.description ? ` · ${c.description}` : ""}
                  {c.receipt ? ` · ${t.costs.receipt}` : ""}
                </span>
              ))}
              {[...totals].map(([currency, sum]) => (
                <span key={currency} className="mt-1 block tabular" style={{ fontWeight: 700 }}>
                  {t.review.costsTotal} {sum.toFixed(2)} {currency}
                </span>
              ))}
            </>
          )}
        </Summary>

        <Summary label={t.review.documents}>
          {uploads.length ? (
            uploads.join(", ")
          ) : (
            <span style={{ color: "var(--text-muted)" }}>לא הועלו מסמכים</span>
          )}
        </Summary>
      </dl>

      {claim ? (
        <p className="mt-6 text-caption" style={{ color: "var(--text-muted)" }}>
          {t.review.reference} <strong className="tabular">{claim.reference}</strong>
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
  /* Not `uppercase`, and not micro.
   *
   * The labels are Hebrew. Hebrew has no case, so `uppercase` does nothing
   * -- but the 0.08em tracking that comes with that size does, and
   * tracked-out Hebrew at 11px is hard to read on a phone. The label of a
   * field somebody is filling in with a passport number should not be the
   * smallest text on the screen.
   */
  return (
    <span
      className="block text-caption font-bold"
      style={{ color: "var(--text-muted)" }}
    >
      {text}
    </span>
  );
}

function Hint({ id, children }: { id: string; children?: string }) {
  if (!children) return null;
  return (
    <span
      id={id}
      className="mt-1.5 block text-caption"
      style={{ color: "var(--text-muted)" }}
    >
      {children}
    </span>
  );
}

/** A labelled control that is not an <input>: select, textarea. */
function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: (id: string, describedBy: string | undefined) => React.ReactNode;
}) {
  const id = useId();
  const hintId = `${id}-hint`;
  return (
    <div>
      <label htmlFor={id} className="block">
        <Label text={label} />
      </label>
      {children(id, hint ? hintId : undefined)}
      <Hint id={hintId}>{hint}</Hint>
    </div>
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
  const id = useId();
  const hintId = `${id}-hint`;

  /*
    The hint is a DESCRIPTION, not part of the label, and the difference is not
    cosmetic: nesting it inside <label> makes the field's accessible name
    "Email This is where we send updates about the claim", which is what a
    screen reader then reads out every time focus lands there.
    aria-describedby keeps the name short and announces the hint after it.
  */
  return (
    <div>
      <label htmlFor={id} className="block">
        <Label text={label} />
      </label>
      <input
        id={id}
        type={type}
        value={value}
        placeholder={placeholder}
        aria-describedby={hint ? hintId : undefined}
        onChange={(e) => onChange(e.target.value)}
        className={`${s.field} mt-2 w-full px-4 py-3.5 text-body ${uppercase ? "uppercase tabular" : ""}`}
      />
      <Hint id={hintId}>{hint}</Hint>
    </div>
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
