import Image from "next/image";

import { FlightBoard } from "@/components/Board";
import { GoogleRating } from "@/components/GoogleRating";
import { FlightPath } from "@/components/FlightPath";
import { Reveal } from "@/components/Reveal";
import { SiteFooter } from "@/components/SiteFooter";
import { Bands } from "@/components/Bands";
import { CheckForm } from "@/components/CheckForm";
import { Faq } from "@/components/Faq";
import s from "@/components/hero.module.css";
import { resolveBackendOrigin } from "@/lib/backend-origin";
import { strings } from "@/lib/strings";

/**
 * The landing page.
 *
 * A server component. Only three things on it need JavaScript -- the check
 * form, the board and the FAQ -- and each is its own client island, so the
 * hero, the bands and everything about the lawyer render as HTML and are
 * readable before a single script has loaded.
 *
 * The page is Hebrew and the document is dir="rtl", so the reading order runs
 * right to left: in every split section below, the FIRST element in the
 * source is the one that appears on the RIGHT. That is why the hero's
 * headline comes before the portrait in the markup and appears beside it on
 * the reader's starting side.
 */

/**
 * Wake the backend while the visitor is still reading.
 *
 * A service that has been quiet takes a moment to start. Without this, the
 * page loads instantly -- the frontend is awake, it just served it -- and
 * then the first check waits on a backend that has not, which reads as the
 * product being broken rather than asleep.
 *
 * Fired and forgotten as the page renders. It is not awaited and its failure
 * is ignored: this is a nudge, not a dependency.
 */
function wakeTheBackend(): void {
  const backend = process.env.BACKEND_ORIGIN;
  if (!backend) return;
  void fetch(`${resolveBackendOrigin(backend)}/health`, {
    cache: "no-store",
  }).catch(() => {});
}

export default function Home() {
  wakeTheBackend();

  return (
    <>
      <Reveal />
      <Hero />
      <TrustStrip />
      <CheckSection />
      <FlightBoard />
      <Bands />
      <Frameworks />
      <Lawyer />
      <HowItWorks />
      <Why />
      <Reviews />
      <Cases />
      <Faq />
      <FinalCta />
      <SiteFooter />
    </>
  );
}

/* --- hero ----------------------------------------------------------------- */

function Hero() {
  const h = strings.hero;

  return (
    /**
     * Centred, and with no photograph.
     *
     * The portrait was the first thing on the page and it was answering a
     * question nobody had yet. A visitor arrives holding "was my flight
     * cancelled, and do I get anything" -- not "who represents me". The face
     * matters enormously at the point where they are deciding whether to hand
     * over a passport number, which is why it still opens the section about
     * him, further down and after the answer.
     *
     * What replaces it is space. Gyro's hero is one centred sentence on a
     * gradient with nothing competing, and it works because the headline is
     * the entire message.
     */
    <section className="field relative overflow-hidden px-5 pb-24 pt-16 sm:px-8 sm:pb-32 sm:pt-24">
      <FlightPath />

      <div className="relative z-10 mx-auto max-w-3xl text-center">
        <span
          className={`${s.rise} inline-flex items-center gap-2 rounded-full px-4 py-2 text-caption`}
          style={{ background: "var(--surface-ink)", color: "var(--text-on-ink)" }}
        >
          <ShieldIcon />
          {h.badge}
        </span>

        <h1
          className={`${s.rise} ${s.d1} mt-7 text-display`}
          style={{ color: "var(--text-strong)" }}
        >
          {h.headlineA}
          <br />
          {h.headlineB}
        </h1>

        <p data-reveal data-delay="2" className={`${s.accent} ${s.rise} ${s.d2} mt-4 text-title`}>
          {h.accent}
        </p>

        <p
          className={`${s.rise} ${s.d3} mx-auto mt-6 max-w-xl text-body`}
          style={{ color: "var(--text-muted)" }}
        >
          {h.subhead}
        </p>

        <div
          className={`${s.rise} ${s.d4} mt-10 flex flex-wrap items-center justify-center gap-5`}
        >
          <a
            href="#check"
            className={`${s.cta} ${s.ctaPill} press px-8 py-4 text-subhead`}
          >
            {h.cta}
            <ArrowIcon />
          </a>
          <a href="#board" className={`${s.navLink} text-callout`}>
            {h.secondaryCta} ←
          </a>
        </div>

        <p
          className={`${s.rise} ${s.d4} mt-6 text-caption`}
          style={{ color: "var(--text-muted)" }}
        >
          {h.reassurance}
        </p>

        <div className={`${s.rise} ${s.d4} mt-8 flex justify-center`}>
          <GoogleRating />
        </div>
      </div>
    </section>
  );
}

/* --- trust strip ----------------------------------------------------------- */

function TrustStrip() {
  return (
    <section className={`${s.trustStrip} px-5 sm:px-8`}>
      <div className="mx-auto grid max-w-6xl grid-cols-2 lg:grid-cols-4">
        {strings.trust.map((item) => (
          <div key={item.label} className={s.trustCell}>
            <TrustIcon kind={item.icon} />
            <p className="mt-2 text-heading font-black" style={{ color: "var(--text-strong)" }}>
              {item.value}
            </p>
            <p className="mt-1 text-caption" style={{ color: "var(--text-muted)" }}>
              {item.label}
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}

function TrustIcon({ kind }: { kind: string }) {
  const teal = "var(--color-teal-400)";
  if (kind === "stars") {
    return (
      <span className="flex justify-center gap-0.5" aria-hidden>
        {[0, 1, 2, 3, 4].map((i) => (
          <svg key={i} width="13" height="13" viewBox="0 0 24 24" fill={teal}>
            <path d="m12 2 3 6.6 7 .9-5.1 4.9 1.3 7-6.2-3.4L5.8 21.4l1.3-7L2 9.5l7-.9L12 2Z" />
          </svg>
        ))}
      </span>
    );
  }
  const paths: Record<string, string> = {
    people: "M16 19v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 9a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm13 10v-2a4 4 0 0 0-3-3.9",
    trend: "M3 17 9 11l4 4 8-8M21 7v5h-5",
    star: "m12 2 3 6.6 7 .9-5.1 4.9 1.3 7-6.2-3.4L5.8 21.4l1.3-7L2 9.5l7-.9L12 2Z",
  };
  return (
    <svg
      width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden
      className="mx-auto" style={{ color: teal }}
    >
      <path d={paths[kind] ?? paths.star} stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/* --- the check, dressed as a boarding pass -------------------------------- */

function CheckSection() {
  const c = strings.check;

  return (
    <section id="check" className={`${s.mist} px-5 py-20 sm:px-8 sm:py-24`}>
      <div className="mx-auto max-w-2xl text-center">
        <h2 data-reveal className="text-title" style={{ color: "var(--text-strong)" }}>
          {c.eyebrow}
        </h2>
        <p className="mt-3 text-body" style={{ color: "var(--text-muted)" }}>
          {c.lead}
        </p>
      </div>

      <div className={`${s.pass} mx-auto mt-10 max-w-2xl`}>
        <div className={`${s.passStrip} flex items-center justify-between px-6 py-3`}>
          <span className="text-micro">{c.stripBrand}</span>
          <span className="hidden text-micro sm:inline" style={{ opacity: 0.7 }}>
            {c.stripSub}
          </span>
          <span
            className="rounded px-2 py-0.5 text-micro"
            style={{ background: "var(--color-teal-400)", color: "#06201e" }}
          >
            {c.stripFree}
          </span>
        </div>

        <div className={s.passTear} />

        <div className="px-6 py-8 sm:px-10">
          <CheckForm />
        </div>
      </div>

    </section>
  );
}

/* --- the legal frameworks ------------------------------------------------- */

function Frameworks() {
  const f = strings.frameworks;

  return (
    <section className="px-5 py-20 text-center sm:px-8">
      <div className="mx-auto max-w-3xl">
        <ScalesIcon />
        <h2 data-reveal className="mt-5 text-title" style={{ color: "var(--text-strong)" }}>
          {f.title}
        </h2>
        <p className="mt-3 text-body" style={{ color: "var(--text-muted)" }}>
          {f.lead}
        </p>
        <div className="mt-8 flex flex-wrap justify-center gap-3">
          {f.items.map((item) => (
            <span
              key={item}
              className="rounded-full px-4 py-2 text-callout"
              style={{
                border: "1px solid var(--border-default)",
                color: "var(--text-default)",
                background: "var(--surface-card)",
              }}
            >
              {item}
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}

/* --- the lawyer ----------------------------------------------------------- */

function Lawyer() {
  const l = strings.lawyer;

  return (
    <section
      id="about"
      className="fieldInk relative overflow-hidden px-5 py-20 sm:px-8 sm:py-28"
      style={{ color: "var(--text-on-ink)" }}
    >
      <div className="mx-auto grid max-w-6xl items-center gap-12 lg:grid-cols-2">
        <div>
          <p className={s.accent + " text-callout font-bold"}>{l.eyebrow}</p>
          <h2 className="mt-3 text-title">{l.name}</h2>
          <p className="mt-3 text-subhead" style={{ color: "var(--text-on-ink-dim)" }}>
            {l.lead}
          </p>
          <p
            className="mt-5 text-body"
            style={{ color: "var(--text-on-ink-dim)", lineHeight: 1.8 }}
          >
            {l.body}
          </p>

          {/* Empty until verified. See the note in strings.ts -- the section
              is designed to read correctly with no figures at all. */}
          {l.credentials.length > 0 ? (
            <div className="mt-8 grid grid-cols-2 gap-3 sm:grid-cols-4">
              {l.credentials.map((c) => (
                <div
                  key={c.label}
                  className="rounded-xl p-4 text-center"
                  style={{ background: "rgb(255 255 255 / 0.05)" }}
                >
                  <p className="text-heading font-black">{c.value}</p>
                  <p className="mt-1 text-caption" style={{ color: "var(--text-on-ink-dim)" }}>
                    {c.label}
                  </p>
                </div>
              ))}
            </div>
          ) : null}

          <div className={`${s.quote} mt-8`}>
            <p className="text-heading font-black">{l.pullQuoteA}</p>
            <p className={`${s.accent} text-heading font-black`}>{l.pullQuoteB}</p>
          </div>
        </div>

        <div className={`${s.portrait} aspect-[4/5] lg:aspect-[5/6]`}>
          <Image
            src="/people/yitzhak-maimon.jpg"
            alt={l.photoAlt}
            fill
            sizes="(max-width: 1024px) 100vw, 520px"
            style={{ objectFit: "cover", objectPosition: "center 12%" }}
          />
          <div className={s.plate}>
            <p className="text-subhead font-black">{l.name}</p>
            <p className="text-caption">{strings.brand.lawyerField}</p>
          </div>
        </div>
      </div>
    </section>
  );
}

/* --- how it works --------------------------------------------------------- */

function HowItWorks() {
  const h = strings.howItWorks;

  return (
    <section id="how" className="px-5 py-20 sm:px-8 sm:py-24">
      <div className="mx-auto max-w-6xl">
        <div className="text-center">
          <h2 data-reveal className="text-title" style={{ color: "var(--text-strong)" }}>
            {h.titleA}
          </h2>
          <p className={`${s.accent} mt-1 text-title`}>{h.titleB}</p>
        </div>

        <ol className="mt-12 grid gap-5 md:grid-cols-3">
          {h.steps.map((step, i) => (
            <li key={step.n} data-reveal data-delay={String(i + 1)} className={`${s.step} press rounded-2xl p-7`}>
              <div className="flex items-start justify-between">
                <span className={`${s.stepNum} ${s.code}`}>{step.n}</span>
              </div>
              <h3 className="mt-4 text-heading" style={{ color: "var(--text-strong)" }}>
                {step.title}
              </h3>
              <p className="mt-2 text-callout" style={{ color: "var(--text-muted)" }}>
                {step.body}
              </p>
            </li>
          ))}
        </ol>

        <div className="mt-10 text-center">
          <a href="#check" className={`${s.cta} ${s.ctaPill} press px-7 py-3.5 text-subhead`}>
            {h.cta}
            <ArrowIcon />
          </a>
        </div>
      </div>
    </section>
  );
}

/* --- why us --------------------------------------------------------------- */

function Why() {
  const w = strings.why;

  return (
    <section className={`${s.mist} px-5 py-20 sm:px-8`}>
      <div className="mx-auto max-w-5xl text-center">
        <h2 data-reveal className="text-title" style={{ color: "var(--text-strong)" }}>
          {w.title}
        </h2>
        <p className={`${s.accent} mt-1 text-title`}>{w.lead}</p>

        <div className="mt-12 grid gap-5 md:grid-cols-3">
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
      </div>
    </section>
  );
}

/* --- reviews --------------------------------------------------------------- */

function Reviews() {
  const r = strings.reviews;

  return (
    <section className={`${s.mist} px-5 py-20 text-center sm:px-8`}>
      <div className="mx-auto max-w-2xl">
        <h2 data-reveal className="text-title" style={{ color: "var(--text-strong)" }}>
          {r.title}
        </h2>
        <p
          data-reveal
          className="mx-auto mt-4 max-w-xl text-body"
          style={{ color: "var(--text-muted)" }}
        >
          {r.lead}
        </p>
        <div data-reveal data-delay="1" className="mt-8 flex justify-center">
          <GoogleRating />
        </div>
        <p className="mt-4 text-caption" style={{ color: "var(--text-muted)" }}>
          {r.readAll} ←
        </p>
      </div>
    </section>
  );
}

/* --- what counts ---------------------------------------------------------- */

function Cases() {
  const c = strings.cases;

  return (
    <section className="px-5 py-20 sm:px-8">
      <div className="mx-auto max-w-4xl text-center">
        <h2 data-reveal className="text-title" style={{ color: "var(--text-strong)" }}>
          {c.title}
        </h2>
        <ul className="mt-8 flex flex-wrap justify-center gap-3">
          {c.items.map((item) => (
            <li
              key={item}
              className="rounded-full px-4 py-2 text-callout"
              style={{
                background: "var(--verdict-yes-fill)",
                border: "1px solid var(--verdict-yes-edge)",
                color: "var(--color-teal-900)",
              }}
            >
              {item}
            </li>
          ))}
        </ul>
        <p className="mt-9 text-heading" style={{ color: "var(--text-strong)" }}>
          {c.unsure}
        </p>
        <p className={`${s.accent} text-heading font-black`}>{c.unsureBody}</p>
      </div>
    </section>
  );
}

/* --- final call ----------------------------------------------------------- */

function FinalCta() {
  const f = strings.finalCta;

  return (
    <section
      className="fieldInk relative overflow-hidden px-5 py-20 text-center sm:px-8 sm:py-28"
      style={{ color: "var(--text-on-ink)" }}
    >
      <div className="mx-auto max-w-2xl">
        <span
          className="inline-block rounded-full px-3.5 py-1.5 text-caption"
          style={{ background: "rgb(255 255 255 / 0.08)" }}
        >
          {f.badge}
        </span>
        <h2 className="mt-5 text-title">{f.title}</h2>
        <p className={`${s.accent} mt-1 text-title`}>{f.lead}</p>
        <p className="mt-5 text-body" style={{ color: "var(--text-on-ink-dim)" }}>
          {f.body}
        </p>
        <div className="mt-8">
          <a href="#check" className={`${s.ctaOnInk} ${s.ctaPill} press px-7 py-3.5 text-subhead`}>
            {strings.hero.cta}
            <ArrowIcon />
          </a>
        </div>
      </div>
    </section>
  );
}

/* --- icons ---------------------------------------------------------------- */

function ShieldIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M12 2 4 5v6c0 5 3.4 9.4 8 11 4.6-1.6 8-6 8-11V5l-8-3Z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
      <path d="m9 12 2 2 4-4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function ArrowIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M19 12H5m6-7-7 7 7 7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function ScalesIcon() {
  return (
    <svg width="34" height="34" viewBox="0 0 24 24" fill="none" aria-hidden className="mx-auto" style={{ color: "var(--color-teal-400)" }}>
      <path d="M12 3v18M7 21h10M3 7h18M6 7l-3 6h6L6 7Zm12 0-3 6h6l-3-6Z" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
