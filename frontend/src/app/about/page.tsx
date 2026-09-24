import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";

import { GoogleRating } from "@/components/GoogleRating";
import { PageHead } from "@/components/PageHead";
import { Reveal } from "@/components/Reveal";
import { SiteFooter } from "@/components/SiteFooter";
import s from "@/components/hero.module.css";
import { strings } from "@/lib/strings";

export const metadata: Metadata = {
  title: 'עו״ד יצחק מימון — מי עומד מאחורי Skyclaim',
  description:
    "Skyclaim נשענת על עו״ד יצחק מימון, המתמחה בדיני תעופה ובזכויות " +
    "נוסעים. מייצגים נוסעים בלבד — לא חברות תעופה.",
};

export default function AboutPage() {
  const l = strings.lawyer;

  return (
    <>
      <Reveal />
      <PageHead eyebrow={strings.nav.about} title={l.name} lead={l.lead} />

      <section className="px-5 pb-16 sm:px-8">
        <div className="mx-auto grid max-w-5xl items-start gap-10 lg:grid-cols-[1fr_0.9fr]">
          <div>
            <p
              data-reveal
              className="text-body"
              style={{ color: "var(--text-default)", lineHeight: 1.85 }}
            >
              {l.body}
            </p>

            {/* Empty until verified -- see strings.ts. The page reads
                correctly with no figures at all. */}
            {l.credentials.length > 0 ? (
              <div className="mt-8 grid grid-cols-2 gap-3 sm:grid-cols-4">
                {l.credentials.map((c) => (
                  <div key={c.label} className={`${s.bandCard}`}>
                    <p className="text-heading font-black">{c.value}</p>
                    <p className="mt-1 text-caption" style={{ color: "var(--text-muted)" }}>
                      {c.label}
                    </p>
                  </div>
                ))}
              </div>
            ) : null}

            <div
              className="mt-8 rounded-2xl p-6"
              style={{ background: "var(--surface-ink)", color: "var(--text-on-ink)" }}
            >
              <p className="text-heading font-black">{l.pullQuoteA}</p>
              <p className={`${s.accent} text-heading font-black`}>{l.pullQuoteB}</p>
            </div>

            <div className="mt-8 flex flex-wrap items-center gap-4">
              <Link href="/#check" className={`${s.cta} ${s.ctaPill} press px-7 py-3.5 text-subhead`}>
                {strings.hero.cta}
              </Link>
              <GoogleRating />
            </div>
          </div>

          <div className={`${s.portrait} aspect-[4/5]`}>
            <Image
              src="/people/yitzhak-maimon.jpg"
              alt={l.photoAlt}
              fill
              priority
              sizes="(max-width: 1024px) 100vw, 480px"
              style={{ objectFit: "cover", objectPosition: "center 12%" }}
            />
            <div className={s.plate}>
              <p className="text-subhead font-black">{l.name}</p>
              <p className="text-caption">{strings.brand.lawyerField}</p>
            </div>
          </div>
        </div>
      </section>

      <SiteFooter />
    </>
  );
}
