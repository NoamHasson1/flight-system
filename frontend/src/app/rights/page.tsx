import type { Metadata } from "next";
import Link from "next/link";

import { FlightPath } from "@/components/FlightPath";
import { Reveal } from "@/components/Reveal";
import { SiteFooter } from "@/components/SiteFooter";
import s from "@/components/hero.module.css";
import { resolveBackendOrigin } from "@/lib/backend-origin";
import { strings } from "@/lib/strings";

export const metadata: Metadata = {
  title: 'הזכויות שלכם — חוק טיבי, EC261 ו-UK261 | Skyclaim',
  description:
    "מה מגיע לכם כשטיסה מתבטלת או מתעכבת: חוק שירותי תעופה הישראלי, התקנה " +
    "האירופית EC261 והחוק הבריטי — הסכומים, הסייגים והתיישנות, בשפה פשוטה.",
};

/**
 * RENDERED PER REQUEST, NOT AT BUILD TIME.
 *
 * `revalidate` alone makes this a static page generated during `next build`.
 * That build runs in its own container, where the backend does not exist --
 * so the fetch below fails, the fallback renders an empty page, and the
 * EMPTY page is what gets cached and shipped. Not a risk: a certainty, and a
 * silent one, because the build succeeds and the page returns 200.
 *
 * Caught here by the figures being missing locally. The same thing would have
 * reached production looking exactly like a page nobody had finished.
 *
 * Per-request costs a few milliseconds -- the backend is on the private
 * network -- and means the page is right whenever the backend is up, and
 * degrades to its heading when it is not.
 */
export const dynamic = "force-dynamic";

type Band = { up_to_km: number | null; amount: string; currency: string };
type Regulation = {
  key: string;
  threshold_hours: number;
  measured_at: string;
  bands: Band[];
};

const SYMBOL: Record<string, string> = { ILS: "₪", EUR: "€", GBP: "£" };

/**
 * The figures, read from the engine that applies them.
 *
 * Returns null rather than throwing. A page explaining the law is still worth
 * reading without the table of amounts; a 500 because a sidecar was slow is
 * not. The table simply does not render.
 */
async function loadRegulations(): Promise<Regulation[] | null> {
  try {
    const response = await fetch(
      `${resolveBackendOrigin(process.env.BACKEND_ORIGIN)}/api/v1/regulations`,
      { cache: "no-store" },
    );
    if (!response.ok) return null;
    return (await response.json()).regulations as Regulation[];
  } catch {
    return null;
  }
}

export default async function RightsPage() {
  const r = strings.rights;
  const regulations = await loadRegulations();
  const byKey = new Map((regulations ?? []).map((x) => [x.key, x]));

  return (
    <>
      <Reveal />

      <section className="field relative overflow-hidden px-5 pb-16 pt-24 sm:px-8 sm:pb-24 sm:pt-32">
        <FlightPath />
        <div className="relative z-10 mx-auto max-w-3xl text-center">
          <p className={`${s.rise} ${s.accent} text-micro uppercase`}>{r.eyebrow}</p>
          <h1 className={`${s.rise} ${s.d1} mt-4 text-display`} style={{ color: "var(--text-strong)" }}>
            {r.title}
          </h1>
          <p
            className={`${s.rise} ${s.d2} mx-auto mt-6 max-w-2xl text-body`}
            style={{ color: "var(--text-muted)" }}
          >
            {r.lead}
          </p>
        </div>
      </section>

      {/* --- which law applies ------------------------------------------- */}
      <section className="px-5 py-16 sm:px-8 sm:py-20">
        <div className="mx-auto max-w-5xl">
          <h2 data-reveal className="text-title" style={{ color: "var(--text-strong)" }}>
            {r.whichApplies.title}
          </h2>
          <p data-reveal className="mt-3 text-body" style={{ color: "var(--text-muted)" }}>
            {r.whichApplies.lead}
          </p>

          <div className="mt-10 grid gap-6">
            {r.laws.map((law, i) => {
              const figures = byKey.get(law.key);
              return (
                <article
                  key={law.key}
                  data-reveal
                  data-delay={String(Math.min(i + 1, 5))}
                  className={`${s.lawCard}`}
                >
                  <div className="flex flex-wrap items-baseline gap-3">
                    <span className={s.lawBadge}>{law.badge}</span>
                    <h3 className="text-heading" style={{ color: "var(--text-strong)" }}>
                      {law.name}
                    </h3>
                    {law.alias ? (
                      <span className="text-callout" style={{ color: "var(--text-muted)" }}>
                        {law.alias}
                      </span>
                    ) : null}
                  </div>

                  <p className="mt-4 text-subhead" style={{ color: "var(--text-strong)" }}>
                    {law.covers}
                  </p>
                  <p className="mt-3 text-callout" style={{ color: "var(--text-muted)", lineHeight: 1.75 }}>
                    {law.detail}
                  </p>

                  <ul className="mt-5 flex flex-wrap gap-2">
                    {law.triggers.map((trigger) => (
                      <li key={trigger} className={s.trigger}>
                        {trigger}
                      </li>
                    ))}
                  </ul>

                  {figures ? (
                    <div className={`${s.thresholdStrip} mt-6`}>
                      <span className="text-caption" style={{ color: "var(--text-muted)" }}>
                        {r.amounts.threshold}
                      </span>
                      <span className={`${s.code} text-heading`} style={{ color: "var(--color-teal-600)" }}>
                        {figures.threshold_hours}
                      </span>
                      <span className="text-callout" style={{ color: "var(--text-default)" }}>
                        {r.amounts.hours} ·{" "}
                        {figures.measured_at === "departure"
                          ? r.amounts.measuredDeparture
                          : r.amounts.measuredArrival}
                      </span>
                    </div>
                  ) : null}

                  {law.note ? (
                    <p className={`${s.noteBox} mt-5`}>{law.note}</p>
                  ) : null}
                </article>
              );
            })}
          </div>
        </div>
      </section>

      {/* --- how much ----------------------------------------------------- */}
      {regulations ? (
        <section className={`${s.mist} px-5 py-16 sm:px-8 sm:py-20`}>
          <div className="mx-auto max-w-5xl">
            <h2 data-reveal className="text-title" style={{ color: "var(--text-strong)" }}>
              {r.amounts.title}
            </h2>
            <p data-reveal className="mt-3 max-w-2xl text-body" style={{ color: "var(--text-muted)" }}>
              {r.amounts.lead}
            </p>

            <div className="mt-10 grid gap-5 md:grid-cols-3">
              {regulations.map((regulation, i) => (
                <div
                  key={regulation.key}
                  data-reveal
                  data-delay={String(i + 1)}
                  className={`${s.bandCard} press text-start`}
                >
                  <p className="text-micro uppercase" style={{ color: "var(--color-teal-600)" }}>
                    {regulation.key === "ISRAEL" ? "חוק שירותי תעופה" : regulation.key}
                  </p>
                  <ul className="mt-4 grid gap-3">
                    {regulation.bands.map((band, index) => (
                      <li key={index} className="flex items-baseline justify-between gap-3">
                        <span className="text-caption" style={{ color: "var(--text-muted)" }}>
                          {bandLabel(r.amounts, regulation.bands, index)}
                        </span>
                        <span
                          className={`${s.code} text-heading`}
                          style={{ color: "var(--text-strong)" }}
                        >
                          {SYMBOL[band.currency] ?? ""}
                          {band.amount}
                        </span>
                      </li>
                    ))}
                  </ul>
                  <p className="mt-4 text-caption" style={{ color: "var(--text-muted)" }}>
                    {r.amounts.perPassenger}
                  </p>
                </div>
              ))}
            </div>

            <p data-reveal className={`${s.noteBox} mt-8`}>
              {r.amounts.familyNote}
            </p>
            <p className="mt-4 text-caption" style={{ color: "var(--text-muted)" }}>
              {r.amounts.sourceNote}
            </p>
          </div>
        </section>
      ) : null}

      {/* --- what blocks it ----------------------------------------------- */}
      <section className="px-5 py-16 sm:px-8 sm:py-20">
        <div className="mx-auto max-w-5xl">
          <h2 data-reveal className="text-title" style={{ color: "var(--text-strong)" }}>
            {r.blockers.title}
          </h2>
          <p data-reveal className="mt-3 max-w-2xl text-body" style={{ color: "var(--text-muted)" }}>
            {r.blockers.lead}
          </p>

          <div className="mt-10 grid gap-5 md:grid-cols-3">
            {r.blockers.items.map((item, i) => (
              <div
                key={item.title}
                data-reveal
                data-delay={String(i + 1)}
                className={`${s.blockCard} press`}
              >
                <h3 className="text-heading" style={{ color: "var(--text-strong)" }}>
                  {item.title}
                </h3>
                <p className="mt-3 text-callout" style={{ color: "var(--text-muted)", lineHeight: 1.7 }}>
                  {item.body}
                </p>
                {/* The caveat is the useful half. An airline leans on these
                    exemptions hardest in exactly the cases where they do not
                    apply, so the qualification gets its own emphasis rather
                    than trailing the paragraph. */}
                <p className={`${s.caveat} mt-4`}>{item.caveat}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* --- the right to care -------------------------------------------- */}
      <section
        className="fieldInk relative overflow-hidden px-5 py-16 sm:px-8 sm:py-20"
        style={{ color: "var(--text-on-ink)" }}
      >
        <div className="mx-auto max-w-4xl">
          <h2 data-reveal className="text-title">
            {r.alsoOwed.title}
          </h2>
          <p data-reveal className="mt-3 max-w-2xl text-body" style={{ color: "var(--text-on-ink-dim)" }}>
            {r.alsoOwed.lead}
          </p>
          <ul className="mt-8 grid gap-3 sm:grid-cols-2">
            {r.alsoOwed.items.map((item, i) => (
              <li
                key={item}
                data-reveal
                data-delay={String(Math.min(i + 1, 5))}
                className="flex items-start gap-3 rounded-xl p-4"
                style={{ background: "rgb(255 255 255 / 0.05)" }}
              >
                <Tick />
                <span className="text-callout">{item}</span>
              </li>
            ))}
          </ul>
          <p className={`${s.quote} mt-8 text-subhead`}>{r.alsoOwed.receipts}</p>
        </div>
      </section>

      {/* --- call to action ------------------------------------------------ */}
      <section className={`${s.mist} px-5 py-20 text-center sm:px-8`}>
        <div className="mx-auto max-w-2xl">
          <h2 className="text-title" style={{ color: "var(--text-strong)" }}>
            {r.cta.title}
          </h2>
          <p className="mt-3 text-body" style={{ color: "var(--text-muted)" }}>
            {r.cta.lead}
          </p>
          <Link href="/#check" className={`${s.cta} ${s.ctaPill} press mt-8 px-8 py-4 text-subhead`}>
            {r.cta.button}
          </Link>
          <p className="mt-8 text-caption" style={{ color: "var(--text-muted)" }}>
            {r.disclaimer}
          </p>
        </div>
      </section>

      <SiteFooter />
    </>
  );
}

/** "עד 2,000 ק״מ" / "2,000–4,500 ק״מ" / "מעל 4,500 ק״מ". */
function bandLabel(
  copy: typeof strings.rights.amounts,
  bands: Band[],
  index: number,
): string {
  const km = (n: number) => n.toLocaleString("en-US");
  const current = bands[index];
  if (index === 0) return copy.upTo.replace("{n}", km(current.up_to_km!));
  if (current.up_to_km === null) {
    return copy.over.replace("{n}", km(bands[index - 1].up_to_km!));
  }
  return copy.between
    .replace("{a}", km(bands[index - 1].up_to_km!))
    .replace("{b}", km(current.up_to_km));
}

function Tick() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden className="mt-0.5 shrink-0">
      <circle cx="12" cy="12" r="10" fill="var(--color-teal-400)" opacity="0.18" />
      <path d="m8 12 3 3 5-6" stroke="var(--color-teal-400)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
