/**
 * A fan of boarding passes, bleeding off the bottom of a band.
 *
 * WHY REAL CARDS AND NOT A PICTURE
 *
 * They are built from divs and CSS, so they stay sharp on any screen,
 * cost nothing to download, and read the right way round in a
 * right-to-left document without anybody having to mirror an image.
 *
 * It is also honest about what it is: a boarding pass is the single most
 * recognisable object in air travel, and the one the customer will be
 * holding when they come to use this site. Using the real anatomy -- the
 * airport code large, the time and date under it, flight and gate and
 * seat in a row, a perforated tear and a barcode -- is what makes it read
 * as a ticket at a glance instead of as three grey rectangles.
 *
 * DECORATION, AND MARKED AS SUCH. `aria-hidden`, pointer events off. The
 * codes are real airports and the rest is plausible nonsense, so a screen
 * reader announcing "LHR 14:30 gate 32C" would be reading out a flight
 * that does not exist to somebody who cannot see that it is scenery.
 *
 * A server component: static markup, no JavaScript.
 */

import s from "./boarding.module.css";

type Pass = {
  city: string;
  code: string;
  time: string;
  date: string;
  flight: string;
  gate: string;
  seat: string;
};

/**
 * Three passes, each a route Ben Gurion actually flies.
 *
 * Not London and New York, which is what a stock illustration would use.
 * Somebody scanning this page has flown one of these, and recognising the
 * route is the difference between decoration and "this is about me".
 */
const PASSES: Pass[] = [
  {
    city: "לונדון",
    code: "LHR",
    time: "14:30",
    date: "12.05.2026",
    flight: "LY315",
    gate: "C4",
    seat: "26A",
  },
  {
    city: "לרנקה",
    code: "LCA",
    time: "09:05",
    date: "03.06.2026",
    flight: "IZ162",
    gate: "B7",
    seat: "10D",
  },
  {
    city: "אתונה",
    code: "ATH",
    time: "17:45",
    date: "21.06.2026",
    flight: "A3929",
    gate: "D2",
    seat: "16C",
  },
];

export function BoardingPasses({ className = "" }: { className?: string }) {
  return (
    <div className={`${s.fan} ${className}`} aria-hidden>
      {PASSES.map((pass, i) => (
        <article key={pass.code} className={`${s.pass} ${s[`pass${i}`]}`}>
          <div className={s.body}>
            <p className={s.city}>{pass.city}</p>
            <div className={s.codeRow}>
              <span className={s.code}>{pass.code}</span>
              <span className={s.arrow} aria-hidden>
                <ArrowDashes />
              </span>
            </div>

            <p className={s.time}>
              <span className={s.caret}>↗</span> {pass.time}
            </p>
            <p className={s.date}>{pass.date}</p>

            <div className={s.rule} />

            <dl className={s.meta}>
              <div>
                <dt>טיסה</dt>
                <dd>{pass.flight}</dd>
              </div>
              <div>
                <dt>שער</dt>
                <dd>{pass.gate}</dd>
              </div>
              <div>
                <dt>מושב</dt>
                <dd>{pass.seat}</dd>
              </div>
            </dl>
          </div>

          {/* The tear line, as the holes a real perforation leaves. */}
          <div className={s.perforation} />
          <Barcode />
        </article>
      ))}
    </div>
  );
}

/** The dashes between origin and destination on a real stub. */
function ArrowDashes() {
  return (
    <svg viewBox="0 0 64 10" className={s.arrowSvg}>
      <line
        x1="2"
        y1="5"
        x2="46"
        y2="5"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeDasharray="3 4"
        strokeLinecap="round"
      />
      <path
        d="M48 1 L56 5 L48 9"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/**
 * Bars of varying width, from a fixed list rather than Math.random().
 *
 * A random barcode would differ between the server render and the
 * browser's, which React reports as a hydration mismatch -- a real error
 * in the console for a purely decorative stripe.
 */
const BARS = [
  3, 1, 2, 1, 1, 4, 1, 2, 3, 1, 1, 2, 4, 1, 2, 1, 3, 2, 1, 1, 4, 2, 1, 3, 1, 1,
  2, 1, 4, 1, 2, 3, 1, 2, 1, 1, 3, 4, 1, 2,
];

function Barcode() {
  return (
    <div className={s.barcode}>
      {BARS.map((width, i) => (
        <span key={i} style={{ width: `${width}px` }} />
      ))}
    </div>
  );
}
