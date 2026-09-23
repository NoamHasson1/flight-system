"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { checkEligibility, type FlightOption } from "@/lib/api";
import { strings } from "@/lib/strings";

import s from "./hero.module.css";

type State =
  | { phase: "idle" }
  | { phase: "checking" }
  | { phase: "choose"; options: FlightOption[]; message: string }
  | { phase: "problem"; messages: string[] };

/** Matches the backend's rule, so a typo is caught before a round trip. */
const FLIGHT_NUMBER = /^[A-Z0-9]{2}[A-Z]?\d{1,4}[A-Z]?$/;

const normalise = (value: string) =>
  value.replace(/[\s\-_.]/g, "").toUpperCase();

/** How long a check may run before the button explains itself. */
const SLOW_AFTER_MS = 5_000;

export function CheckForm() {
  const router = useRouter();
  const [flightNumber, setFlightNumber] = useState("");
  const [flightDate, setFlightDate] = useState("");
  const [state, setState] = useState<State>({ phase: "idle" });
  /**
   * Validation appears only after a field has been left or a submit attempted.
   * Telling somebody their flight number is wrong while they are still typing
   * the second character is correct and useless.
   */
  const [touched, setTouched] = useState<Record<string, boolean>>({});
  const numberRef = useRef<HTMLInputElement>(null);

  const today = new Date().toISOString().slice(0, 10);
  const cleaned = normalise(flightNumber);

  const numberError = !cleaned
    ? strings.errors.flightNumberRequired
    : !FLIGHT_NUMBER.test(cleaned)
      ? strings.errors.flightNumberFormat
      : null;
  const dateError = !flightDate
    ? strings.errors.dateRequired
    : flightDate > today
      ? strings.errors.dateFuture
      : null;

  const busy = state.phase === "checking";

  /**
   * True once a check has been running long enough that a silent spinner
   * starts to read as a broken page.
   *
   * The wait is real and the answer is coming: on a free host the backend
   * stops after a quarter of an hour of quiet and takes the better part of a
   * minute to wake, and the browser now waits long enough to let it. What
   * this fixes is not the delay but the SILENCE -- somebody watching nothing
   * happen for thirty seconds closes the tab, and a closed tab is a claim
   * nobody ever hears about.
   *
   * Five seconds because a normal check takes under two, so anything past
   * five is already unusual enough to deserve a word.
   */
  const [slow, setSlow] = useState(false);

  useEffect(() => {
    if (!busy) return;
    const timer = setTimeout(() => setSlow(true), SLOW_AFTER_MS);
    return () => clearTimeout(timer);
  }, [busy]);

  async function run(optionKey?: string) {
    setTouched({ flightNumber: true, flightDate: true });
    if (numberError || dateError) {
      numberRef.current?.focus();
      return;
    }

    setSlow(false);
    setState({ phase: "checking" });

    const result = await checkEligibility({
      flight_number: cleaned,
      flight_date: flightDate,
      option_key: optionKey ?? null,
    });

    if (!result.ok) {
      setState({
        phase: "problem",
        messages:
          result.failure.kind === "invalid" && result.failure.messages.length
            ? result.failure.messages
            : [strings.errors.unreachable],
      });
      return;
    }

    if (result.data.status === "AMBIGUOUS") {
      // Never guess which flight was theirs. Two services can share a number
      // on one date, and picking the first tells half of those passengers a
      // confident answer about a journey they did not take.
      setState({
        phase: "choose",
        options: result.data.options ?? [],
        message: result.data.message ?? strings.result.ambiguousExplain,
      });
      return;
    }

    // Every other outcome -- decided, not found, or unresolved -- has been
    // stored and has an id, so it gets a URL that can be reloaded, shared and
    // sent to support.
    router.push(`/check/${result.data.check_id}`);
  }

  return (
    <div id="check" className={`${s.card} ${s.rise} ${s.d4} w-full p-6 text-left sm:p-8`}>
      <h2
        className="text-heading"
        style={{ color: "var(--text-strong)", fontFamily: "var(--font-display-stack)" }}
      >
        {strings.hero.cardTitle}
      </h2>
      {state.phase === "choose" ? (
        <ChooseFlight
          options={state.options}
          message={state.message}
          onPick={(key) => void run(key)}
          onBack={() => setState({ phase: "idle" })}
        />
      ) : (
        <form
          noValidate
          onSubmit={(event) => {
            event.preventDefault();
            void run();
          }}
          className="mt-5"
        >
          <div className="grid gap-4 sm:grid-cols-[1.1fr_1fr]">
            <Field
              label={strings.form.flightNumberLabel}
              error={touched.flightNumber ? numberError : null}
            >
              <input
                ref={numberRef}
                name="flightNumber"
                value={flightNumber}
                onChange={(e) => setFlightNumber(e.target.value)}
                onBlur={() => setTouched((t) => ({ ...t, flightNumber: true }))}
                placeholder={strings.form.flightNumberPlaceholder}
                autoComplete="off"
                autoCapitalize="characters"
                spellCheck={false}
                aria-invalid={touched.flightNumber && !!numberError}
                aria-describedby={numberError ? "flight-number-error" : undefined}
                /* Autofocus is usually a nuisance. Here the page exists to
                   receive this one value, the field is above the fold, and
                   nothing is scrolled past to reach it -- so the cursor
                   starting in it saves everyone a click. */
                autoFocus
                className={`${s.field} tabular mt-2 w-full px-4 py-3.5 text-subhead uppercase`}
              />
            </Field>

            <Field
              label={strings.form.dateLabel}
              error={touched.flightDate ? dateError : null}
            >
              <input
                name="flightDate"
                type="date"
                max={today}
                value={flightDate}
                onChange={(e) => setFlightDate(e.target.value)}
                onBlur={() => setTouched((t) => ({ ...t, flightDate: true }))}
                aria-invalid={touched.flightDate && !!dateError}
                className={`${s.field} tabular mt-2 w-full px-4 py-3.5 text-subhead`}
              />
            </Field>
          </div>


          <button
            type="submit"
            disabled={busy}
            className={`${s.cta} mt-5 w-full px-6 py-4 text-subhead`}
            style={{ fontFamily: "var(--font-display-stack)", fontWeight: 700 }}
          >
            {busy && <Spinner />}
            {busy
              ? slow
                ? strings.form.submittingSlow
                : strings.form.submitting
              : strings.form.submit}
          </button>

          {state.phase === "problem" ? (
            <div
              role="alert"
              className="mt-4 rounded-xl px-4 py-3 text-callout"
              style={{
                background: "var(--verdict-review-fill)",
                border: "1px solid var(--verdict-review-edge)",
                color: "var(--verdict-review)",
              }}
            >
              {state.messages.map((message) => (
                <p key={message}>{message}</p>
              ))}
            </div>
          ) : (
            <p
              className="mt-4 flex items-center justify-center gap-2 text-caption"
              style={{ color: "var(--text-muted)" }}
            >
              <svg viewBox="0 0 24 24" className="size-4" fill="none" stroke="currentColor"
                   strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                <rect x="4" y="10" width="16" height="10" rx="2" />
                <path d="M8 10V7a4 4 0 0 1 8 0v3" />
              </svg>
              {strings.hero.reassurance}
            </p>
          )}
        </form>
      )}
    </div>
  );
}

function Field({
  label,
  error,
  children,
}: {
  label: string;
  error: string | null;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span
        className="text-micro uppercase"
        style={{ color: "var(--text-muted)" }}
      >
        {label}
      </span>
      {children}
      {/* Always rendered, visually hidden when empty, so a screen reader
          announces the message as it appears rather than only when focus
          lands on the field. */}
      <span
        role="alert"
        aria-live="polite"
        className={error ? "mt-1.5 block text-caption" : "sr-only"}
        style={{ color: "var(--verdict-review)" }}
      >
        {error ?? ""}
      </span>
    </label>
  );
}

function ChooseFlight({
  options,
  message,
  onPick,
  onBack,
}: {
  options: FlightOption[];
  message: string;
  onPick: (key: string) => void;
  onBack: () => void;
}) {
  return (
    <div>
      <h2
        className="text-heading"
        style={{ fontFamily: "var(--font-display-stack)", color: "var(--text-strong)" }}
      >
        {strings.result.ambiguousLead}
      </h2>
      <p className="mt-2 text-callout" style={{ color: "var(--text-muted)" }}>
        {message}
      </p>

      <ul className="mt-5 space-y-3">
        {options.map((option) => (
          <li key={option.key}>
            <button
              type="button"
              onClick={() => onPick(option.key)}
              className={`${s.field} w-full cursor-pointer px-4 py-3.5 text-left text-subhead`}
            >
              {option.label}
            </button>
          </li>
        ))}
      </ul>

      <button
        type="button"
        onClick={onBack}
        className="mt-5 text-callout underline underline-offset-4"
        style={{ color: "var(--text-muted)" }}
      >
        Search a different flight
      </button>
    </div>
  );
}

function Spinner() {
  return (
    <svg
      className="size-4 animate-spin"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden
    >
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity="0.25" strokeWidth="3" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}
