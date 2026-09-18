import Link from "next/link";

import s from "@/components/hero.module.css";
import { getCheck, type EligibilityResponse, type Outcome } from "@/lib/api";
import { strings } from "@/lib/strings";

/**
 * The result.
 *
 * Its own URL rather than state on the landing page, so it can be reloaded,
 * bookmarked, sent to a partner and pasted into a support email. A verdict
 * about money that vanishes on refresh is a verdict people cannot act on.
 *
 * Rendered from the STORED check rather than a fresh lookup. The answer has to
 * be the one this person was actually given -- flight data gets corrected, and
 * showing someone a different verdict for the same link would be indefensible.
 *
 * Provisional styling: the designed version comes in step 23, after you have
 * picked a direction from the mockups.
 */

export const dynamic = "force-dynamic";

type Params = { params: Promise<{ checkId: string }> };

export default async function CheckResult({ params }: Params) {
  const { checkId } = await params;
  const result = await getCheck(checkId);

  if (!result.ok) {
    return (
      <Shell>
        <Lead
          eyebrow="Sorry"
          title={
            result.failure.kind === "notFound"
              ? "We can't find that check"
              : "We couldn't load this"
          }
        />
        <p className="mt-4 text-body" style={{ color: "var(--hero-ink-dim)" }}>
          {result.failure.kind === "notFound"
            ? "The link may be wrong, or the check may have been removed."
            : strings.errors.unreachable}
        </p>
        <Again />
      </Shell>
    );
  }

  const check = result.data;

  if (check.status === "NOT_FOUND") {
    return (
      <Shell>
        <Lead eyebrow="Checked" title={strings.result.notFoundLead} />
        <p className="mt-4 text-body" style={{ color: "var(--hero-ink-dim)" }}>
          {check.message}
        </p>
        <Again />
      </Shell>
    );
  }

  const verdict = (check.verdict ?? "NEEDS_REVIEW") as keyof typeof strings.verdict;
  const tone = TONES[verdict];
  const copy = strings.verdict[verdict];

  return (
    <Shell>
      <Lead eyebrow={copy.eyebrow} title={copy.lead} tone={tone} />

      {check.best_award ? (
        <p
          className="mt-6 text-display tabular"
          style={{ fontFamily: "var(--font-sans-stack)", fontWeight: 700, color: tone.ink }}
        >
          {check.best_award.formatted}
          <span
            className="ml-3 align-middle text-subhead"
            style={{ color: "var(--hero-ink-dim)", fontWeight: 500 }}
          >
            {strings.verdict.ELIGIBLE.underAmount} {check.best_regulation}
          </span>
        </p>
      ) : null}

      {check.message ? (
        <p className="mt-5 max-w-prose text-body" style={{ color: "var(--hero-ink-dim)" }}>
          {check.message}
        </p>
      ) : null}

      {check.flight ? <FlightCard check={check} /> : null}

      {check.outcomes.length ? (
        <section className="mt-10">
          <h2 className="text-heading" style={{ fontFamily: "var(--font-display-stack)" }}>
            {strings.result.regulationsChecked}
          </h2>
          <ul className="mt-4 space-y-3">
            {check.outcomes.map((outcome) => (
              <OutcomeRow key={outcome.regulation} outcome={outcome} />
            ))}
          </ul>
        </section>
      ) : null}

      {check.caveat ? (
        <section
          className="mt-8 rounded-2xl p-5"
          style={{
            background: "oklch(60% 0.12 70 / 0.12)",
            border: "1px solid oklch(70% 0.10 70 / 0.28)",
          }}
        >
          <h3 className="text-subhead" style={{ color: "oklch(90% 0.06 80)" }}>
            {strings.result.caveatTitle}
          </h3>
          <p className="mt-2 text-callout" style={{ color: "oklch(84% 0.04 80)" }}>
            {check.caveat}
          </p>
        </section>
      ) : null}

      <div className="mt-10 flex flex-wrap items-center gap-4">
        {verdict !== "NOT_ELIGIBLE" ? (
          <span className={`${s.cta} px-6 py-3.5 text-subhead`} style={{ fontWeight: 700 }}>
            {strings.result.startClaim} — step 24
          </span>
        ) : null}
        <Again inline />
      </div>

      <p className="mt-10 text-caption" style={{ color: "var(--hero-ink-dim)" }}>
        {strings.legal.disclaimer}
      </p>
    </Shell>
  );
}

// --- pieces ------------------------------------------------------------------

const TONES = {
  ELIGIBLE: { ink: "oklch(86% 0.16 155)", fill: "oklch(60% 0.13 155 / 0.14)", edge: "oklch(70% 0.12 155 / 0.32)" },
  NOT_ELIGIBLE: { ink: "oklch(88% 0.01 285)", fill: "oklch(70% 0.01 285 / 0.10)", edge: "oklch(75% 0.01 285 / 0.22)" },
  NEEDS_REVIEW: { ink: "oklch(88% 0.11 82)", fill: "oklch(65% 0.12 75 / 0.14)", edge: "oklch(75% 0.11 75 / 0.30)" },
} as const;

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className={`${s.hero} min-h-dvh`}>
      <header className={`${s.nav} sticky top-0 z-50 px-5 py-3 sm:px-8`}>
        <Link href="/" className="text-subhead" style={{ fontFamily: "var(--font-display-stack)", fontWeight: 700 }}>
          {strings.brand.name}
        </Link>
      </header>
      <main className={`${s.rise} ${s.d1} mx-auto max-w-2xl px-5 py-14 sm:px-8`}>{children}</main>
    </div>
  );
}

function Lead({
  eyebrow,
  title,
  tone,
}: {
  eyebrow: string;
  title: string;
  tone?: (typeof TONES)[keyof typeof TONES];
}) {
  return (
    <>
      <p className="text-micro uppercase" style={{ color: tone?.ink ?? "var(--hero-ink-dim)", letterSpacing: "0.12em" }}>
        {eyebrow}
      </p>
      <h1 className="mt-3 text-title text-balance" style={{ fontFamily: "var(--font-display-stack)", fontWeight: 680 }}>
        {title}
      </h1>
    </>
  );
}

function FlightCard({ check }: { check: EligibilityResponse }) {
  const f = check.flight!;
  const rows: Array<[string, string]> = [
    ["Flight", `${f.flight_number} · ${f.airline}`],
    ["Route", `${f.route} · ${Math.round(f.distance_km).toLocaleString()} km`],
    ["Departed", f.departure_delay_hours === null ? "—" : hours(f.departure_delay_hours)],
    ["Arrived", f.arrival_delay_hours === null ? "—" : hours(f.arrival_delay_hours)],
  ];
  return (
    <section className={`${s.glass} mt-8 p-5 sm:p-6`}>
      <dl className="grid gap-x-8 gap-y-3 sm:grid-cols-2">
        {rows.map(([label, value]) => (
          <div key={label}>
            <dt className="text-micro uppercase" style={{ color: "var(--hero-ink-dim)" }}>
              {label}
            </dt>
            <dd className="tabular mt-1 text-subhead">{value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function OutcomeRow({ outcome }: { outcome: Outcome }) {
  const tone = TONES[(outcome.verdict as keyof typeof TONES) ?? "NOT_ELIGIBLE"];
  return (
    <li className="rounded-2xl p-4 sm:p-5" style={{ background: tone.fill, border: `1px solid ${tone.edge}` }}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="text-subhead" style={{ color: tone.ink, fontFamily: "var(--font-display-stack)", fontWeight: 620 }}>
          {outcome.regulation}
        </span>
        <span className="text-caption" style={{ color: "var(--hero-ink-dim)" }}>
          {/* `applies` separates "this law does not cover you" from "it covers
              you but you did not qualify". Without it a row of three NOs looks
              like the same answer three times. */}
          {outcome.applies ? strings.result.appliesYes : strings.result.appliesNo}
        </span>
      </div>
      {outcome.award ? (
        <p className="tabular mt-1 text-heading" style={{ color: tone.ink, fontWeight: 700 }}>
          {outcome.award.formatted}
        </p>
      ) : null}
      <p className="mt-2 text-callout" style={{ color: "var(--hero-ink-dim)" }}>
        {outcome.reason}
      </p>
    </li>
  );
}

function Again({ inline }: { inline?: boolean }) {
  return (
    <Link
      href="/"
      className={inline ? "text-callout underline underline-offset-4" : "mt-8 inline-block text-callout underline underline-offset-4"}
      style={{ color: "var(--hero-ink-dim)" }}
    >
      {strings.result.checkAnother}
    </Link>
  );
}

function hours(value: number): string {
  const total = Math.round(Math.abs(value) * 60);
  const sign = value < 0 ? "−" : "";
  return `${sign}${Math.floor(total / 60)}h ${String(total % 60).padStart(2, "0")}m late`;
}
