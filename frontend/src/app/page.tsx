import s from "@/components/hero.module.css";

/**
 * The landing hero.
 *
 * Structure follows Latebird rather than Gyro: headline, then the form itself
 * on the first screen. Gyro puts a button there and the form one click later,
 * which suits a marketing site. This is a tool somebody opens because
 * something has already gone wrong, so the fastest thing it can do is let them
 * start typing.
 *
 * The form is visual only at this step; it is wired to the API in step 22.
 *
 * A server component with CSS entrance animations, deliberately. The first
 * version used Motion springs and rendered a completely blank page: the server
 * emitted the initial opacity: 0, hydration never happened, and nothing
 * animated it back. Springs are worth their cost for things a person can grab
 * and reverse; an entrance fade is not one of those, and paying for it with the
 * page's visibility is a bad trade.
 */
export default function Home() {
  return (
    <div className={s.hero}>
      {/* Translucent chrome with the hero passing underneath it. */}
      <header
        className={`${s.nav} sticky top-0 z-50 flex items-center justify-between px-5 py-3 sm:px-8`}
      >
        <a href="/" className="flex items-center gap-2.5">
          <span
            aria-hidden
            className="grid size-7 place-items-center rounded-full"
            style={{ background: "var(--hero-ink)", color: "var(--hero-base)" }}
          >
            <svg viewBox="0 0 24 24" className="size-4" fill="currentColor">
              <path d="M21 16v-2l-8-5V3.5a1.5 1.5 0 0 0-3 0V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5z" />
            </svg>
          </span>
          <span
            className="text-subhead"
            style={{ fontFamily: "var(--font-display-stack)", fontWeight: 700 }}
          >
            Skyclaim
          </span>
        </a>

        <nav className="hidden items-center gap-7 text-callout md:flex" style={{ color: "var(--hero-ink-dim)" }}>
          {["How it works", "Your rights", "Airlines"].map((item) => (
            <a key={item} href="#" className="transition-colors hover:text-white">
              {item}
            </a>
          ))}
        </nav>

        <a href="#check" className={`${s.navCta} px-4 py-2 text-callout font-medium`}>
          Check a flight
        </a>
      </header>

      <main className="mx-auto flex min-h-[calc(100dvh-3.5rem)] max-w-3xl flex-col items-center justify-center px-5 pb-20 pt-14 text-center sm:px-8">
        {/* Eyebrow: names the three laws up front. The specificity is the point
            — "we check three regulations" is a claim anybody can verify, where
            "get what you deserve" is a claim about nothing. */}
        <p
                    className={`${s.rise} ${s.d1} text-micro uppercase`}
          style={{ color: "var(--hero-ink-dim)", letterSpacing: "0.12em" }}
        >
          EC261 · UK261 · Israeli Aviation Services Law
        </p>

        <h1
                    className={`${s.rise} ${s.d2} mt-5 text-display text-balance`}
          style={{ fontFamily: "var(--font-display-stack)", fontWeight: 700 }}
        >
          Flight delayed?
          <br />
          You may be owed
          <br />
          {/* The amount renders in Inter, not the display face. Plus Jakarta
              Sans has no shekel glyph, so the browser substitutes one from a
              fallback font — and the substitute arrives at a different weight
              and width, which reads as a typo in the middle of the headline.
              Inter carries ₪, € and £ and has tabular figures. */}
          up to{" "}
          <span
            className="tabular"
            style={{ fontFamily: "var(--font-sans-stack)", fontWeight: 700 }}
          >
            ₪3,670
          </span>
          .
        </h1>

        <p
                    className={`${s.rise} ${s.d3} mt-6 max-w-xl text-subhead text-pretty`}
          style={{ color: "var(--hero-ink-dim)", fontWeight: 400 }}
        >
          Enter your flight number and the date it departed. We check what
          actually happened to that flight against all three regulations and
          show you the reasoning — not just a yes or no.
        </p>

        {/* The form: the fastest thing this page can do is let them type. */}
        <form
          id="check"
          className={`${s.glass} ${s.settle} ${s.d4} mt-11 w-full max-w-xl p-5 text-left sm:p-6`}
        >
          <div className="grid gap-4 sm:grid-cols-[1.1fr_1fr]">
            <label className="block">
              <span className={`${s.rise} ${s.d1} text-micro uppercase`} style={{ color: "var(--hero-ink-dim)" }}>
                Flight number
              </span>
              <input
                name="flightNumber"
                placeholder="BA165"
                autoComplete="off"
                autoCapitalize="characters"
                spellCheck={false}
                className={`${s.field} tabular mt-2 w-full px-4 py-3.5 text-subhead`}
              />
            </label>

            <label className="block">
              <span className={`${s.rise} ${s.d1} text-micro uppercase`} style={{ color: "var(--hero-ink-dim)" }}>
                Date it departed
              </span>
              <input
                name="flightDate"
                type="date"
                className={`${s.field} tabular mt-2 w-full px-4 py-3.5 text-subhead`}
              />
            </label>
          </div>

          {/* type="button", not "submit": this is a server component and the
              form is not wired until step 22. A submit button in a form with no
              action reloads the page, which would look like a broken product
              rather than an unfinished one. */}
          <button
            type="button"
            className={`${s.cta} mt-5 w-full px-6 py-4 text-subhead`}
            style={{ fontFamily: "var(--font-display-stack)", fontWeight: 700 }}
          >
            See what you&rsquo;re owed
          </button>

          {/* Reassurance directly under the action, where the hesitation is.
              Both references do this and both are right to. */}
          <p className="mt-4 text-center text-caption" style={{ color: "var(--hero-ink-dim)" }}>
            Free · No account · No card · Takes about ten seconds
          </p>
        </form>

        {/* Honest instead of impressive. A brand-new product claiming "50,000
            travellers" is lying, and the one thing this product sells is being
            trusted about money. */}
        <p
                    className={`${s.rise} ${s.d5} mt-8 text-caption`}
          style={{ color: "var(--hero-ink-dim)" }}
        >
          Every answer shows which law applied, which did not, and why.
        </p>
      </main>
    </div>
  );
}
