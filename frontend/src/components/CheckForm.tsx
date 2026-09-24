"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { checkEligibility, type FlightOption } from "@/lib/api";
import { airlineName, cityName } from "@/lib/names";
import { strings } from "@/lib/strings";

import s from "./hero.module.css";

type State =
  | { phase: "idle" }
  | { phase: "checking" }
  | { phase: "choose"; options: FlightOption[]; message: string }
  /**
   * The flight was found, and we are asking whether it is theirs BEFORE
   * showing what it is worth.
   *
   * A flight number is reused -- LY315 flies most days -- so somebody who
   * mistypes the date gets a real flight that is not theirs. Without this
   * step they would read a confident verdict about a journey they never
   * took, and the dangerous half of that is a "no" shown to somebody who is
   * in fact owed money.
   */
  | { phase: "confirm"; checkId: string; flight: FlightSummary }
  | { phase: "problem"; messages: string[] };

type FlightSummary = {
  flight_number: string;
  airline: string | null;
  origin: string | null;
  destination: string | null;
};

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

    // A decided check with an identified flight gets the confirmation step.
    // Everything else -- not found, unresolved -- goes straight through:
    // there is no flight to confirm, and asking "is this yours?" about a
    // flight we could not find would be a nonsense question.
    const flight = result.data.flight;
    if (result.data.status === "DECIDED" && flight?.origin && flight?.destination) {
      setState({
        phase: "confirm",
        checkId: result.data.check_id,
        flight: {
          flight_number: flight.flight_number,
          airline: flight.airline ?? null,
          origin: flight.origin,
          destination: flight.destination,
        },
      });
      return;
    }

    // Stored and given an id, so it gets a URL that can be reloaded, shared
    // and sent to support.
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
      {state.phase === "confirm" ? (
        <ConfirmFlight
          flight={state.flight}
          onYes={() => router.push(`/check/${state.checkId}`)}
          onNo={() => setState({ phase: "idle" })}
        />
      ) : state.phase === "choose" ? (
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

/**
 * "We found this flight. Is it yours?"
 *
 * Shown AFTER the check has run but BEFORE the verdict, which is the only
 * ordering that works: we cannot describe the flight without looking it up,
 * and we must not price a journey somebody did not take.
 *
 * The route is drawn rather than written -- two cities with a dashed line and
 * an aeroplane between them -- because that is the shape of a boarding pass
 * and it is recognised faster than "TLV → LHR" is read.
 */
function ConfirmFlight({
  flight,
  onYes,
  onNo,
}: {
  flight: FlightSummary;
  onYes: () => void;
  onNo: () => void;
}) {
  const c = strings.confirm;
  return (
    <div className="mt-6">
      <p className="flex items-center gap-2 text-callout" style={{ color: "var(--color-teal-600)" }}>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
          <path d="m5 13 4 4L19 7" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        {c.found}
      </p>

      <div className={`${s.foundCard} mt-4`}>
        <div className="flex items-baseline justify-between gap-4">
          <span className={`${s.code} text-title`} style={{ color: "var(--text-strong)" }}>
            {flight.flight_number}
          </span>
          {flight.airline ? (
            <span className="text-callout" style={{ color: "var(--text-muted)" }}>
              {airlineName(flight.airline)}
            </span>
          ) : null}
        </div>

        <div className="mt-5 flex items-center justify-between gap-4">
          <span className="text-heading" style={{ color: "var(--text-strong)" }}>
            {cityName(flight.origin)}
          </span>
          <span className={s.routeLine} aria-hidden>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
              <path d="M21 16v-2l-8-5V3.5a1.5 1.5 0 0 0-3 0V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5L21 16Z" />
            </svg>
          </span>
          <span className="text-heading" style={{ color: "var(--text-strong)" }}>
            {cityName(flight.destination)}
          </span>
        </div>
      </div>

      <p className="mt-6 text-center text-callout" style={{ color: "var(--text-muted)" }}>
        {c.question}
      </p>

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        {/* "Yes" leads, because it is the answer nine times in ten. "No"
            is a plain button rather than a quiet link: somebody who got the
            wrong flight must be able to leave without hunting. */}
        <button type="button" onClick={onYes} className={`${s.cta} press w-full px-6 py-3.5 text-subhead`}>
          {c.yes}
        </button>
        <button type="button" onClick={onNo} className={`${s.ghost} press w-full px-6 py-3.5 text-subhead`}>
          {c.no}
        </button>
      </div>
    </div>
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
