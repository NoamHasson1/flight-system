/**
 * The design system, visible.
 *
 * Not decoration: a page where every token is rendered next to its name is how
 * a system stays coherent. A colour nobody can find gets reinvented, and two
 * greens that are almost the same is how an interface stops looking designed.
 *
 * Lives at /styleguide and is not linked from the product.
 */

const TYPE = [
  ["display", "Are you owed money?", "-0.022em / 1.05"],
  ["title", "Your flight was 4 hours late", "-0.018em / 1.12"],
  ["heading", "What happens next", "-0.011em / 1.28"],
  ["subhead", "Three regulations were checked", "-0.006em / 1.40"],
  ["body", "Compensation is fixed by distance, not by how late you were. This paragraph is body copy at the size most of the interface uses.", "0 / 1.58"],
  ["callout", "Under UK261, arriving three hours late is the threshold.", "0.002em / 1.50"],
  ["caption", "This is an automated estimate, not legal advice.", "0.006em / 1.45"],
  ["micro", "FLIGHT NUMBER", "0.020em / 1.40"],
] as const;

const VERDICTS = [
  {
    name: "Eligible",
    token: "eligible",
    note: "A considered green, not a celebratory one. This is a legal finding, not a prize.",
  },
  {
    name: "Not eligible",
    token: "neutralv",
    note: "Deliberately NOT red. It is an answer, not an error, and the person reading it did nothing wrong.",
  },
  {
    name: "Needs review",
    token: "review",
    note: "Amber: something is pending. Nobody has failed and nothing is denied.",
  },
] as const;

export default function StyleGuide() {
  return (
    <main className="mx-auto max-w-3xl px-6 py-16">
      <header className="mb-16">
        <p className="text-micro uppercase text-faint">Design system</p>
        <h1 className="text-display text-strong mt-2" style={{ fontFamily: "var(--font-display-stack)" }}>Tokens</h1>
        <p className="text-body text-muted mt-4 max-w-prose">
          Every value here is a deliberate choice with a reason beside it. A
          token nobody can justify is a token somebody will change for no
          reason.
        </p>
      </header>

      {/* --- Type --- */}
      <section className="mb-16">
        <h2 className="text-heading text-strong">Type</h2>
        <p className="text-callout text-muted mt-2 mb-8 max-w-prose">
          Size, tracking and leading are one decision made per step. Tracking
          goes negative as text grows — letters read too far apart at display
          sizes — and slightly positive as it shrinks. A single letter-spacing
          for every size is wrong somewhere.
        </p>
        <div className="space-y-7">
          {TYPE.map(([name, sample, metrics]) => (
            <div key={name}>
              <div className="flex items-baseline gap-3 mb-1">
                <code className="text-micro uppercase text-brand-600">
                  {name}
                </code>
                <span className="text-micro text-faint tabular">{metrics}</span>
              </div>
              <p
                className="text-strong"
                /* fontSize, not the `font` shorthand: `font: 3.75rem` with no
                   family is invalid CSS and is silently dropped, which is
                   exactly how a type scale ends up looking like one size. */
                style={{
                  fontSize: `var(--text-${name})`,
                  letterSpacing: `var(--text-${name}--letter-spacing)`,
                  lineHeight: `var(--text-${name}--line-height)`,
                  fontWeight: `var(--text-${name}--font-weight, 400)`,
                  /* Display and title carry the expressive face; everything
                     working stays on Inter, which is more legible small and
                     has dependable tabular figures. */
                  fontFamily:
                    name === "display" || name === "title"
                      ? "var(--font-display-stack)"
                      : "var(--font-sans-stack)",
                }}
              >
                {sample}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* --- Verdicts --- */}
      <section className="mb-16">
        <h2 className="text-heading text-strong">Verdict colours</h2>
        <p className="text-callout text-muted mt-2 mb-6 max-w-prose">
          The most important colour decision in the product.
        </p>
        <div className="space-y-4">
          {VERDICTS.map((v) => (
            <div
              key={v.token}
              className="rounded-lg border p-5"
              style={{
                background: `var(--color-${v.token}-50)`,
                borderColor: `var(--color-${v.token}-200)`,
              }}
            >
              <p
                className="text-subhead"
                style={{ color: `var(--color-${v.token}-700)` }}
              >
                {v.name}
              </p>
              <p
                className="text-callout mt-1"
                style={{ color: `var(--color-${v.token}-600)` }}
              >
                {v.note}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* --- Surfaces --- */}
      <section className="mb-16">
        <h2 className="text-heading text-strong">Surfaces &amp; depth</h2>
        <p className="text-callout text-muted mt-2 mb-6 max-w-prose">
          Bigger surfaces read as thicker: stronger blur and a deeper shadow
          than a small chip. Shadows are layered and tinted with the surface hue
          rather than pure black, which reads as grime on a light background.
        </p>
        <div className="grid gap-4 sm:grid-cols-3">
          {[
            ["card", "--shadow-card", "Resting"],
            ["raised", "--shadow-raised", "Lifted"],
            ["overlay", "--shadow-overlay", "Floating"],
          ].map(([key, shadow, label]) => (
            <div
              key={key}
              className="rounded-lg bg-card p-5 border border-subtle"
              style={{ boxShadow: `var(${shadow})` }}
            >
              <p className="text-subhead text-strong">{label}</p>
              <code className="text-micro text-faint">{shadow}</code>
            </div>
          ))}
        </div>
      </section>

      {/* --- Material --- */}
      <section className="mb-16">
        <h2 className="text-heading text-strong">Translucent material</h2>
        <p className="text-callout text-muted mt-2 mb-6 max-w-prose">
          Chrome is a floating layer with content scrolling underneath, not an
          opaque strip that consumes a fixed band of the screen. The bright top
          edge is light catching the edge of a real material.
        </p>
        <div className="relative h-44 overflow-hidden rounded-lg bg-brand-100">
          <div className="p-5 text-callout text-brand-900">
            Content sits underneath and scrolls past. Lorem ipsum dolor sit
            amet, consectetur adipiscing elit, sed do eiusmod tempor.
          </div>
          <div
            className="absolute inset-x-0 bottom-0 p-4"
            style={{
              background: "var(--material-thin)",
              backdropFilter: "blur(var(--material-blur)) saturate(180%)",
              borderTop: "1px solid var(--material-edge)",
            }}
          >
            <p className="text-callout text-strong">
              Translucent toolbar — blurred, saturated, bright top edge
            </p>
          </div>
        </div>
      </section>

      {/* --- Motion --- */}
      <section className="mb-16">
        <h2 className="text-heading text-strong">Motion</h2>
        <p className="text-callout text-muted mt-2 mb-6 max-w-prose">
          Springs, not durations, for anything a person can touch — a spring can
          be grabbed and reversed mid-flight; a keyframe animation has to finish
          first. Bounce is reserved for motion that carried momentum: overshoot
          on a menu that merely faded in feels like a toy.
        </p>
        <dl className="text-callout grid grid-cols-[auto_1fr] gap-x-6 gap-y-2">
          {[
            ["spring", "bounce 0 · 0.4s", "default, nothing thrown"],
            ["springQuick", "bounce 0 · 0.28s", "small elements"],
            ["springSheet", "bounce 0.2 · 0.32s", "sheets — dragged, so earned"],
            ["springMomentum", "bounce 0.25 · 0.4s", "released after a flick"],
          ].map(([name, params, use]) => (
            <div key={name} className="contents">
              <dt className="text-brand-600 tabular">{name}</dt>
              <dd className="text-muted">
                <span className="tabular">{params}</span> — {use}
              </dd>
            </div>
          ))}
        </dl>
      </section>

      {/* --- Accessibility --- */}
      <section>
        <h2 className="text-heading text-strong">Accessibility</h2>
        <p className="text-callout text-muted mt-2 mb-6 max-w-prose">
          Three independent preferences, three different responses. Reduced
          motion is not &ldquo;animations off&rdquo; — it is a gentler,
          non-vestibular equivalent, so opacity and colour changes that explain
          what just changed stay.
        </p>
        <ul className="text-callout text-muted space-y-2">
          <li>
            <code className="text-brand-600">prefers-reduced-motion</code> —
            travel and overshoot become cross-fades
          </li>
          <li>
            <code className="text-brand-600">prefers-reduced-transparency</code>{" "}
            — materials become solid, blur drops to zero
          </li>
          <li>
            <code className="text-brand-600">prefers-contrast: more</code> —
            text darkens, borders strengthen, translucency goes
          </li>
        </ul>
      </section>
    </main>
  );
}
