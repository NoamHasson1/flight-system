import type { Metadata } from "next";
import Link from "next/link";

import { PageHead } from "@/components/PageHead";
import { Reveal } from "@/components/Reveal";
import { SiteFooter } from "@/components/SiteFooter";
import s from "@/components/hero.module.css";
import { strings } from "@/lib/strings";

export const metadata: Metadata = {
  title: "איך זה עובד — תהליך התביעה | Skyclaim",
  description:
    "שלושה שלבים: מאתרים את הטיסה, בודקים זכאות, ואנחנו מטפלים מול חברת " +
    "התעופה. בלי הרשמה, בלי תשלום מראש.",
};

export default function HowPage() {
  const h = strings.howItWorks;
  const w = strings.why;

  return (
    <>
      <Reveal />
      <PageHead eyebrow={strings.nav.how} title={h.titleA} lead={h.titleB} />

      <section className="px-5 pb-16 sm:px-8">
        <ol className="mx-auto grid max-w-5xl gap-5 md:grid-cols-3">
          {h.steps.map((step, i) => (
            <li
              key={step.n}
              data-reveal
              data-delay={String(i + 1)}
              className={`${s.step} press rounded-2xl p-7`}
            >
              <span className={`${s.stepNum} ${s.code}`}>{step.n}</span>
              <h2 className="mt-4 text-heading" style={{ color: "var(--text-strong)" }}>
                {step.title}
              </h2>
              <p className="mt-2 text-callout" style={{ color: "var(--text-muted)" }}>
                {step.body}
              </p>
            </li>
          ))}
        </ol>
      </section>

      <section className={`${s.mist} px-5 py-16 sm:px-8`}>
        <div className="mx-auto max-w-5xl text-center">
          <h2 data-reveal className="text-title" style={{ color: "var(--text-strong)" }}>
            {w.title}
          </h2>
          <p className={`${s.accent} mt-1 text-title`}>{w.lead}</p>
          <div className="mt-10 grid gap-5 md:grid-cols-3">
            {w.items.map((item, i) => (
              <div
                key={item.title}
                data-reveal
                data-delay={String(i + 1)}
                className="press rounded-2xl p-7"
                style={{
                  background: "var(--surface-card)",
                  border: "1px solid var(--border-subtle)",
                }}
              >
                <h3 className="text-heading" style={{ color: "var(--text-strong)" }}>
                  {item.title}
                </h3>
                <p className="mt-2 text-callout" style={{ color: "var(--text-muted)" }}>
                  {item.body}
                </p>
              </div>
            ))}
          </div>
          <Link href="/#check" className={`${s.cta} ${s.ctaPill} press mt-10 px-8 py-4 text-subhead`}>
            {h.cta}
          </Link>
        </div>
      </section>

      <SiteFooter />
    </>
  );
}
