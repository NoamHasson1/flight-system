import { CheckForm } from "@/components/CheckForm";
import s from "@/components/hero.module.css";
import { strings } from "@/lib/strings";

/**
 * The landing page.
 *
 * Light-first with a dark ink band behind the hero, following the reference.
 * The check card straddles the band's lower edge, which is what makes the form
 * read as the page's purpose rather than as the next section down.
 *
 * A server component: nothing above the form needs JavaScript, so nothing
 * above the form waits for it.
 */
export default function Home() {
  return (
    <>
      <Nav />

      <section className={`${s.band} px-5 pb-36 pt-16 sm:px-8 sm:pb-40 sm:pt-24`}>
        <div className="mx-auto max-w-3xl text-center">
          <p
            className={`${s.rise} ${s.d1} text-micro uppercase`}
            style={{ color: "var(--color-teal-400)" }}
          >
            EC261 · UK261 · Israeli Aviation Services Law
          </p>

          <h1 className={`${s.rise} ${s.d2} mt-5 text-display text-balance`}>
            {strings.hero.headlineA}
            <br />
            <span className={s.accent}>{strings.hero.headlineB}</span>
          </h1>

          <p
            className={`${s.rise} ${s.d3} mx-auto mt-6 max-w-xl text-subhead text-pretty`}
            style={{ color: "var(--text-on-ink-dim)", fontWeight: 400 }}
          >
            {strings.hero.subhead}
          </p>
        </div>
      </section>

      {/* Pulled up over the band. `relative` + a z-index are load-bearing, not
          decoration: the band is position: relative, so it forms a stacking
          context that paints above a statically-positioned sibling. Without
          this the overlap works but the band covers the top of the card, and
          the heading and field labels vanish behind it. */}
      <div className="relative z-10 mx-auto -mt-28 max-w-2xl px-5 sm:px-8">
        <CheckForm />
      </div>

      <Stats />
      <Steps />
      <Footer />
    </>
  );
}

function Nav() {
  return (
    <header className={`${s.nav} px-5 py-3.5 sm:px-8`}>
      <div className="mx-auto flex max-w-6xl items-center justify-between">
        <a href="/" className="flex items-center gap-2.5 no-underline">
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
            style={{ fontFamily: "var(--font-display-stack)", fontWeight: 800, color: "var(--text-strong)" }}
          >
            {strings.brand.name}
          </span>
        </a>

        <nav className="hidden items-center gap-8 text-callout md:flex">
          {["How it works", "Your rights", "Airlines", "About"].map((item) => (
            <a key={item} href="#" className={s.navLink}>
              {item}
            </a>
          ))}
        </nav>

        <a href="#check" className={`${s.ctaPill} px-5 py-2.5 text-callout no-underline`} style={{ fontWeight: 600 }}>
          Check a flight
        </a>
      </div>
    </header>
  );
}

function Stats() {
  return (
    <section className="mx-auto max-w-6xl px-5 py-20 sm:px-8">
      <div className="grid gap-10 sm:grid-cols-2 lg:grid-cols-4">
        {strings.stats.map((stat, i) => (
          <div key={stat.value} className={s.stat}>
            <span className={s.statIcon} aria-hidden>
              <StatIcon index={i} />
            </span>
            <p className="text-subhead" style={{ color: "var(--text-strong)" }}>
              {stat.value}
            </p>
            <p className="text-callout" style={{ color: "var(--text-muted)" }}>
              {stat.label}
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}

/** Line icons on a 24px grid, one stroke weight. Never emoji. */
function StatIcon({ index }: { index: number }) {
  const common = {
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.7,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    className: "size-6",
  };
  if (index === 0)
    return (
      <svg {...common}>
        <circle cx="12" cy="12" r="9" />
        <path d="M15 9.5a3.5 3.5 0 1 0 0 5M9 11h4M9 13.5h4" />
      </svg>
    );
  if (index === 1)
    return (
      <svg {...common}>
        <path d="M4 5h16M4 12h16M4 19h10" />
      </svg>
    );
  if (index === 2)
    return (
      <svg {...common}>
        <path d="M12 3 4 6.5v5c0 4.5 3.2 8.4 8 9.5 4.8-1.1 8-5 8-9.5v-5L12 3Z" />
        <path d="m9 12 2 2 4-4" />
      </svg>
    );
  return (
    <svg {...common}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </svg>
  );
}

function Steps() {
  return (
    <section className={`${s.mist} px-5 py-20 sm:px-8`}>
      <div className="mx-auto max-w-5xl">
        <h2 className="text-title text-center" style={{ color: "var(--text-strong)" }}>
          How it works
        </h2>
        <div className="mt-12 grid gap-5 md:grid-cols-3">
          {strings.steps.map((step) => (
            <div key={step.n} className={`${s.step} p-6`}>
              <span className={s.stepNum}>{step.n}</span>
              <h3 className="mt-4 text-subhead" style={{ color: "var(--text-strong)" }}>
                {step.title}
              </h3>
              <p className="mt-2 text-callout" style={{ color: "var(--text-muted)" }}>
                {step.body}
              </p>
            </div>
          ))}
        </div>
        <div className="mt-10 text-center">
          <a href="#check" className={`${s.cta} px-7 py-4 text-subhead no-underline`}>
            {strings.form.submit}
          </a>
        </div>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className={`${s.band} px-5 py-10 sm:px-8`}>
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4">
        <p className="text-callout" style={{ color: "var(--text-on-ink-dim)" }}>
          {strings.brand.name} — {strings.legal.disclaimer}
        </p>
        <p className="text-caption" style={{ color: "var(--text-on-ink-dim)" }}>
          {strings.brand.tagline}
        </p>
      </div>
    </footer>
  );
}
