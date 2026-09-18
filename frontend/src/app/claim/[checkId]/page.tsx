import Link from "next/link";
import { notFound } from "next/navigation";

import { ClaimWizard } from "@/components/ClaimWizard";
import s from "@/components/hero.module.css";
import { getCheck } from "@/lib/api";
import { strings } from "@/lib/strings";

/**
 * The claim page.
 *
 * A server component that fetches the check, then hands it to the wizard.
 * Doing the fetch here rather than in the client means the page cannot render
 * a claim form for a check that does not exist, and the customer never sees a
 * flash of empty form before it decides.
 */

export const dynamic = "force-dynamic";

type Params = { params: Promise<{ checkId: string }> };

export default async function ClaimPage({ params }: Params) {
  const { checkId } = await params;
  const result = await getCheck(checkId);

  if (!result.ok) {
    if (result.failure.kind === "notFound") notFound();
    return (
      <Shell>
        <p className={`${s.errorBox} px-4 py-3 text-callout`}>
          {strings.errors.unreachable}
        </p>
      </Shell>
    );
  }

  const check = result.data;

  // A check that never identified a flight has nothing to claim about. Note
  // what is NOT refused: NOT_ELIGIBLE. We told that customer no, but the
  // verdict rests on facts we could not see, so it is an estimate rather than
  // the last word.
  if (check.status === "NOT_FOUND" || check.status === "AMBIGUOUS") {
    return (
      <Shell>
        <h1 className="text-title" style={{ color: "var(--text-strong)" }}>
          We need to find your flight first
        </h1>
        <p className="mt-3 text-body" style={{ color: "var(--text-muted)" }}>
          That check didn&rsquo;t identify a flight, so there&rsquo;s nothing to
          claim for yet.
        </p>
        <Link
          href="/"
          className={`${s.cta} mt-7 inline-flex px-7 py-3.5 text-subhead no-underline`}
          style={{ fontWeight: 700 }}
        >
          {strings.result.checkAnother}
        </Link>
      </Shell>
    );
  }

  return (
    <Shell>
      <div className="mb-8">
        <p className="text-micro uppercase" style={{ color: "var(--color-teal-600)" }}>
          {check.flight
            ? `${check.flight.flight_number} · ${check.flight.route}`
            : strings.claim.title}
        </p>
        <h1 className="mt-2 text-title" style={{ color: "var(--text-strong)" }}>
          {strings.claim.title}
        </h1>
        {check.best_award ? (
          <p className="mt-2 text-body" style={{ color: "var(--text-muted)" }}>
            You&rsquo;re claiming{" "}
            <strong className="tabular" style={{ color: "var(--verdict-yes)" }}>
              {check.best_award.formatted}
            </strong>{" "}
            per passenger.
          </p>
        ) : null}
      </div>

      <ClaimWizard check={check} />
    </Shell>
  );
}

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
        </div>
      </header>

      <main className={`${s.rise} ${s.d1} mx-auto max-w-2xl px-5 py-14 sm:px-8`}>
        {children}
      </main>
    </>
  );
}
