import Link from "next/link";

import s from "@/components/hero.module.css";
import { getCheck, type EligibilityResponse } from "@/lib/api";
import { strings } from "@/lib/strings";

/**
 * The result.
 *
 * ONE answer, in plain words. No regulation names, no thresholds, no
 * clause-by-clause reasoning — the customer asked a simple question and gets a
 * simple answer.
 *
 * All of that reasoning is still computed and still stored against the check
 * (`result_detail`), and it is what the admin queue and the claim handler work
 * from. It is simply not what this screen is for. Keeping it in the database
 * and out of the interface is the whole point: nothing is lost, and the person
 * who just wanted to know whether they can claim is not made to read three
 * paragraphs of aviation law to find out.
 *
 * Its own URL rather than state on the landing page, so it survives a refresh
 * and can be bookmarked or sent to a partner. Rendered from the STORED check
 * rather than a fresh lookup: the answer has to be the one this person was
 * actually given.
 */

export const dynamic = "force-dynamic";

type Params = { params: Promise<{ checkId: string }> };

export default async function CheckResult({ params }: Params) {
  const { checkId } = await params;
  const result = await getCheck(checkId);

  if (!result.ok) {
    return (
      <Shell>
        <Eyebrow tone="no">Sorry</Eyebrow>
        <Lead>
          {result.failure.kind === "notFound"
            ? "We can't find that check"
            : "We couldn't load this"}
        </Lead>
        <Body>
          {result.failure.kind === "notFound"
            ? "The link may be wrong, or the check may have been removed."
            : strings.errors.unreachable}
        </Body>
        <Actions primary={null} />
      </Shell>
    );
  }

  const check = result.data;

  if (check.status === "NOT_FOUND") {
    return (
      <Shell>
        <Eyebrow tone="no">Checked</Eyebrow>
        <Lead>{strings.result.notFoundLead}</Lead>
        <Body>{check.message}</Body>
        <Actions primary={null} />
      </Shell>
    );
  }

  const verdict = (check.verdict ?? "NEEDS_REVIEW") as
    | "ELIGIBLE"
    | "LIKELY_ELIGIBLE"
    | "NOT_ELIGIBLE"
    | "NEEDS_REVIEW";

  /**
   * The law covers the flight and the amount is known; one fact is missing,
   * and the person reading this has it.
   *
   * The figure leads, exactly as it does for a settled claim, because that is
   * what is true. What differs is the badge above it and the question below
   * it -- not a smaller, hedged, greyed-out version of the number, which would
   * be a design that disbelieves its own answer.
   */
  if (verdict === "LIKELY_ELIGIBLE") {
    const copy = strings.verdict.LIKELY_ELIGIBLE;
    const asked = (check.open_questions ?? [])
      .map((key) => strings.questions[key as keyof typeof strings.questions])
      .filter(Boolean);

    return (
      <Shell>
        <Eyebrow tone="likely">{copy.eyebrow}</Eyebrow>
        <Lead>{copy.lead}</Lead>

        <p
          className="tabular mt-7 text-display"
          style={{ color: "var(--verdict-yes)", fontFamily: "var(--font-sans-stack)" }}
        >
          {check.best_award?.formatted}
        </p>
        <p className="mt-1 text-subhead" style={{ color: "var(--text-muted)", fontWeight: 500 }}>
          {copy.amountLabel}
        </p>

        {check.flight ? <FlightCard check={check} /> : null}

        {asked.map((question) => (
          <section
            key={question.title}
            className="mt-10 rounded-2xl p-6"
            style={{
              background: "var(--surface-mist)",
              border: "1px solid var(--border-subtle)",
            }}
          >
            <h2 className="text-subhead" style={{ color: "var(--text-strong)" }}>
              {question.title}
            </h2>
            <p className="mt-2 text-callout" style={{ color: "var(--text-muted)" }}>
              {question.explain}
            </p>
          </section>
        ))}

        <Actions primary={strings.result.startClaim} href={`/claim/${checkId}`} />
        <Caveat />
      </Shell>
    );
  }

  if (verdict === "ELIGIBLE") {
    const copy = strings.verdict.ELIGIBLE;
    return (
      <Shell>
        <Eyebrow tone="yes">{copy.eyebrow}</Eyebrow>
        <Lead>{copy.lead}</Lead>

        <p
          className="tabular mt-7 text-display"
          style={{ color: "var(--verdict-yes)", fontFamily: "var(--font-sans-stack)" }}
        >
          {check.best_award?.formatted}
        </p>
        <p className="mt-1 text-subhead" style={{ color: "var(--text-muted)", fontWeight: 500 }}>
          {copy.amountLabel}
        </p>

        {check.flight ? <FlightCard check={check} /> : null}

        <section className="mt-12">
          <h2 className="text-heading" style={{ color: "var(--text-strong)" }}>
            {strings.result.whatNext}
          </h2>
          <ol className="mt-5 flex flex-col gap-4">
            {strings.result.nextSteps.map((step, i) => (
              <li key={step} className="flex items-start gap-3.5">
                <span className={s.stepNum} aria-hidden>
                  {i + 1}
                </span>
                <span className="text-body pt-1" style={{ color: "var(--text-default)" }}>
                  {step}
                </span>
              </li>
            ))}
          </ol>
        </section>

        <Actions primary={strings.result.startClaim} href={`/claim/${checkId}`} />
        <Caveat />
      </Shell>
    );
  }

  if (verdict === "NEEDS_REVIEW") {
    const copy = strings.verdict.NEEDS_REVIEW;
    return (
      <Shell>
        <Eyebrow tone="review">{copy.eyebrow}</Eyebrow>
        <Lead>{copy.lead}</Lead>
        <Body>{copy.body}</Body>
        {check.flight ? <FlightCard check={check} /> : null}
        <Actions primary={strings.result.askHuman} href={`/claim/${checkId}`} />
        <Caveat />
      </Shell>
    );
  }

  const copy = strings.verdict.NOT_ELIGIBLE;
  return (
    <Shell>
      <Eyebrow tone="no">{copy.eyebrow}</Eyebrow>
      <Lead>{copy.lead}</Lead>
      <Body>{copy.body}</Body>
      {check.flight ? <FlightCard check={check} /> : null}

      {/* Our arrival time is touchdown, while the law counts from the doors
          opening. Offering a hand-check is how somebody near the line gets a
          second look instead of closing the tab. */}
      <div
        className="mt-10 rounded-2xl p-6"
        style={{ background: "var(--surface-mist)", border: "1px solid var(--border-subtle)" }}
      >
        <p className="text-subhead" style={{ color: "var(--text-strong)" }}>
          Think that&rsquo;s wrong?
        </p>
        <p className="mt-2 text-callout" style={{ color: "var(--text-muted)" }}>
          {copy.doubt}
        </p>
      </div>

      <Actions primary={strings.result.askHuman} href={`/claim/${checkId}`} />
    </Shell>
  );
}

// --- pieces ------------------------------------------------------------------

const TONE = {
  yes: "var(--verdict-yes)",
  no: "var(--text-muted)",
  review: "var(--verdict-review)",
  /* Teal like a settled yes, not amber like an unfinished lookup: the money
     is real and the law is settled. The hedge belongs in the words, which say
     "almost certainly", not in a colour that undercuts the figure. */
  likely: "var(--verdict-yes)",
} as const;

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <>
      <header className={`${s.nav} px-5 py-3.5 sm:px-8`}>
        <div className="mx-auto flex max-w-6xl items-center justify-between">
          <Link href="/" className="flex items-center gap-2.5 no-underline">
            <span
              aria-hidden
              className="grid size-8 place-items-center rounded-lg"
              style={{ background: "var(--color-teal-600)", color: "#fff" }}
            >
              <svg viewBox="0 0 24 24" className="size-[18px]" fill="currentColor">
                <path d="M21 16v-2l-8-5V3.5a1.5 1.5 0 0 0-3 0V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5z" />
              </svg>
            </span>
            <span
              className="text-subhead"
              style={{
                fontFamily: "var(--font-display-stack)",
                fontWeight: 800,
                color: "var(--text-strong)",
              }}
            >
              {strings.brand.name}
            </span>
          </Link>
          <Link href="/" className={`${s.navLink} text-callout`}>
            {strings.result.checkAnother}
          </Link>
        </div>
      </header>

      <main className={`${s.rise} ${s.d1} mx-auto max-w-2xl px-5 py-16 sm:px-8`}>
        {children}
      </main>
    </>
  );
}

function Eyebrow({ tone, children }: { tone: keyof typeof TONE; children: React.ReactNode }) {
  return (
    <p className="text-micro uppercase" style={{ color: TONE[tone] }}>
      {children}
    </p>
  );
}

function Lead({ children }: { children: React.ReactNode }) {
  return (
    <h1 className="mt-3 text-title text-balance" style={{ color: "var(--text-strong)" }}>
      {children}
    </h1>
  );
}

function Body({ children }: { children: React.ReactNode }) {
  return (
    <p className="mt-5 max-w-prose text-body" style={{ color: "var(--text-muted)" }}>
      {children}
    </p>
  );
}

function FlightCard({ check }: { check: EligibilityResponse }) {
  const f = check.flight!;
  const rows: Array<[string, string]> = [
    ["Flight", `${f.flight_number} · ${f.airline}`],
    ["Route", f.route],
    ["Distance", `${Math.round(f.distance_km).toLocaleString()} km`],
    [
      "Arrived",
      f.arrival_delay_hours === null ? "—" : late(f.arrival_delay_hours),
    ],
  ];
  return (
    <section
      className="mt-10 rounded-2xl p-6"
      style={{ background: "var(--surface-mist)", border: "1px solid var(--border-subtle)" }}
    >
      <p className="text-micro uppercase" style={{ color: "var(--text-muted)" }}>
        {strings.result.yourFlight}
      </p>
      <dl className="mt-4 grid gap-x-8 gap-y-4 sm:grid-cols-2">
        {rows.map(([label, value]) => (
          <div key={label}>
            <dt className="text-caption" style={{ color: "var(--text-muted)" }}>
              {label}
            </dt>
            <dd className="tabular mt-0.5 text-subhead" style={{ color: "var(--text-strong)" }}>
              {value}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function Actions({ primary, href }: { primary: string | null; href?: string }) {
  return (
    <div className="mt-10 flex flex-wrap items-center gap-6">
      {primary && href ? (
        <Link href={href} className={`${s.cta} px-7 py-4 text-subhead no-underline`} style={{ fontWeight: 700 }}>
          {primary}
        </Link>
      ) : null}
      <Link
        href="/"
        className="text-callout underline underline-offset-4"
        style={{ color: "var(--text-muted)" }}
      >
        {strings.result.checkAnother}
      </Link>
    </div>
  );
}

function Caveat() {
  return (
    <p className="mt-10 text-caption" style={{ color: "var(--text-muted)" }}>
      {strings.result.caveat} {strings.legal.disclaimer}
    </p>
  );
}

function late(value: number): string {
  const total = Math.round(Math.abs(value) * 60);
  return `${Math.floor(total / 60)}h ${String(total % 60).padStart(2, "0")}m late`;
}
