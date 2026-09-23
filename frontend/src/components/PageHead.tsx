import { FlightPath } from "@/components/FlightPath";

import s from "./hero.module.css";

/**
 * The top of every page that is not the landing page.
 *
 * One component rather than six copies: the alternative is six hero sections
 * that drift apart in padding and type scale until the site reads as six
 * sites. It also means a new tab cannot ship with a heading that does not
 * match the others.
 *
 * Animated with CSS, not the scroll observer, for the same reason the landing
 * hero is: this is above the fold, and content that waits for JavaScript is
 * content that is blank on a slow connection and missing without one.
 */
export function PageHead({
  eyebrow,
  title,
  lead,
}: {
  eyebrow: string;
  title: string;
  lead?: string;
}) {
  return (
    <section className="field relative overflow-hidden px-5 pb-14 pt-24 sm:px-8 sm:pb-20 sm:pt-32">
      <FlightPath />
      <div className="relative z-10 mx-auto max-w-3xl text-center">
        <p className={`${s.rise} ${s.accent} text-micro uppercase`}>{eyebrow}</p>
        <h1
          className={`${s.rise} ${s.d1} mt-4 text-display`}
          style={{ color: "var(--text-strong)" }}
        >
          {title}
        </h1>
        {lead ? (
          <p
            className={`${s.rise} ${s.d2} mx-auto mt-6 max-w-2xl text-body`}
            style={{ color: "var(--text-muted)" }}
          >
            {lead}
          </p>
        ) : null}
      </div>
    </section>
  );
}
