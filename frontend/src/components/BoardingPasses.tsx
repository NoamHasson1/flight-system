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
  airline: string;
  passenger: string;
  from: string;
  city: string;
  code: string;
  time: string;
  date: string;
  flight: string;
  gate: string;
  seat: string;
  /** The digits printed under a real barcode. */
  serial: string;
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
    airline: "EL AL",
    passenger: "COHEN / DANA",
    from: "TLV",
    city: "לונדון",
    code: "LHR",
    time: "14:30",
    date: "12 MAY 2026",
    flight: "LY315",
    gate: "C4",
    seat: "26A",
    serial: "0 7 1 4 2 9 3 5 8 1",
  },
  {
    airline: "ISRAIR",
    passenger: "LEVI / OMER",
    from: "TLV",
    city: "לרנקה",
    code: "LCA",
    time: "09:05",
    date: "03 JUN 2026",
    flight: "IZ162",
    gate: "B7",
    seat: "10D",
    serial: "0 4 9 8 2 2 6 1 7 3",
  },
  {
    airline: "AEGEAN",
    passenger: "MIZRAHI / NOA",
    from: "TLV",
    city: "אתונה",
    code: "ATH",
    time: "17:45",
    date: "21 JUN 2026",
    flight: "A3929",
    gate: "D2",
    seat: "16C",
    serial: "0 2 6 5 7 4 1 9 0 8",
  },
];

export function BoardingPasses({ className = "" }: { className?: string }) {
  return (
    <div className={`${s.fan} ${className}`} aria-hidden>
      {PASSES.map((pass, i) => (
        <article key={pass.code} className={`${s.pass} ${s[`pass${i}`]}`}>
          {/* The masthead every real pass has: who is flying you, and
              what this piece of card is. Without it the thing reads as a
              receipt. */}
          <header className={s.head}>
            <span className={s.airline}>{pass.airline}</span>
            <span className={s.kind}>BOARDING PASS</span>
          </header>

          <div className={s.body}>
            {/* Origin and destination TOGETHER. A pass shows a journey,
                not a destination -- the first version printed one code
                and an arrow pointing at nothing, which is why it read as
                a luggage tag. */}
            <div className={s.route}>
              <span className={s.endpoint}>
                <span className={s.codeSmall}>{pass.from}</span>
              </span>
              <span className={s.arrow} aria-hidden>
                <ArrowDashes />
              </span>
              <span className={s.endpoint}>
                <span className={s.code}>{pass.code}</span>
                <span className={s.city}>{pass.city}</span>
              </span>
            </div>

            <p className={s.passenger}>{pass.passenger}</p>

            <dl className={s.meta}>
              <div>
                <dt>FLIGHT</dt>
                <dd>{pass.flight}</dd>
              </div>
              <div>
                <dt>DATE</dt>
                <dd className={s.small}>{pass.date}</dd>
              </div>
              <div>
                <dt>BOARDING</dt>
                <dd>{pass.time}</dd>
              </div>
            </dl>

            <dl className={`${s.meta} ${s.metaTight}`}>
              <div>
                <dt>GATE</dt>
                <dd className={s.big}>{pass.gate}</dd>
              </div>
              <div>
                <dt>SEAT</dt>
                <dd className={s.big}>{pass.seat}</dd>
              </div>
              <div>
                <dt>ZONE</dt>
                <dd className={s.big}>2</dd>
              </div>
            </dl>
          </div>

          {/* The tear: two punched notches at the edges and a line of
              holes between them. That silhouette is the single most
              recognisable thing about a boarding pass. */}
          <div className={s.tear}>
            <span className={s.notch} />
            <span className={s.holes} />
            <span className={s.notch} />
          </div>

          <div className={s.stub}>
            <Barcode />
            <p className={s.serial}>{pass.serial}</p>
          </div>
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
