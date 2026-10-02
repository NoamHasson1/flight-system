/**
 * Decoration that moves.
 *
 * Three pieces, in the same spirit as `FlightPath`: a cabin window with the
 * sun going down past it, a bank of clouds drifting, and two distant
 * aircraft crossing with their contrails behind them.
 *
 * EVERY ONE OF THEM IS A SERVER COMPONENT. They are static SVG plus CSS
 * animations, so they cost no JavaScript at all -- which matters on a
 * landing page whose whole job is to load fast enough that somebody
 * anxious about a flight does not give up and go to a competitor.
 *
 * All of it is `aria-hidden` with pointer events off. None of it says
 * anything the text does not, so a screen reader is told to skip it rather
 * than announce a decorative graphic, and none of it can intercept a tap
 * meant for the button underneath.
 *
 * Motion is held to slow, continuous drift. A landing page that flashes and
 * pops reads as a scam, which is the one impression a compensation firm
 * cannot afford -- and the whole file collapses to a still image under
 * `prefers-reduced-motion`, handled in ambience.module.css.
 */

import s from "./ambience.module.css";

/**
 * The view out of a cabin window at sunset.
 *
 * The window is the real shape -- a rounded rectangle far taller than it is
 * wide, with the thick inner surround that every narrowbody has. Getting
 * that silhouette right is what makes it read as a window at a glance
 * rather than as an abstract blob, and it is the single most recognisable
 * image in air travel.
 */
type Decoration = {
  className?: string;
  /** The caller tints and places it; `currentColor` does the rest. */
  style?: React.CSSProperties;
};

export function CabinWindow({ className = "", style }: Decoration) {
  return (
    <div className={`${s.window} ${className}`} style={style} aria-hidden>
      <svg viewBox="0 0 220 300" className={s.windowSvg}>
        <defs>
          {/* The sky, top to bottom: deep dusk into the band of orange that
              sits right on the horizon. */}
          <linearGradient id="amb-sky" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#1b2a44" />
            <stop offset="42%" stopColor="#4a4668" />
            <stop offset="68%" stopColor="#b2694f" />
            <stop offset="84%" stopColor="#e8975a" />
            <stop offset="100%" stopColor="#f6c178" />
          </linearGradient>

          <radialGradient id="amb-sun" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#fff3cf" />
            <stop offset="55%" stopColor="#ffca72" />
            <stop offset="100%" stopColor="#ffb25c" stopOpacity="0" />
          </radialGradient>

          {/* Everything inside the glass is clipped to the glass. Without
              this the sun slides out over the fuselage. */}
          <clipPath id="amb-glass">
            <rect x="34" y="34" width="152" height="232" rx="72" />
          </clipPath>
        </defs>

        <g clipPath="url(#amb-glass)">
          <rect x="34" y="34" width="152" height="232" fill="url(#amb-sky)" />

          {/* The sun sits low and sinks a little, forever. A full sunset
              would be a story with an ending; this is a mood. */}
          <circle className={s.sun} cx="110" cy="196" r="46" fill="url(#amb-sun)" />
          <circle className={s.sun} cx="110" cy="196" r="17" fill="#fff0c4" />

          {/* Cloud deck below, drifting the other way to the sun so the
              movement reads as the aircraft travelling. */}
          <g className={s.deck}>
            <ellipse cx="60" cy="236" rx="78" ry="13" fill="#fdd9a8" opacity="0.55" />
            <ellipse cx="170" cy="248" rx="90" ry="15" fill="#f8c89a" opacity="0.5" />
            <ellipse cx="280" cy="236" rx="78" ry="13" fill="#fdd9a8" opacity="0.55" />
          </g>
          <rect x="34" y="258" width="152" height="12" fill="#c97a52" opacity="0.5" />
        </g>

        {/* The surround, drawn as a thick stroke so the sky shows through
            the middle without a second shape to keep aligned. */}
        <rect
          x="34"
          y="34"
          width="152"
          height="232"
          rx="72"
          fill="none"
          stroke="#e9edf0"
          strokeWidth="18"
        />
        <rect
          x="34"
          y="34"
          width="152"
          height="232"
          rx="72"
          fill="none"
          stroke="#c7ced6"
          strokeWidth="2"
        />

        {/* One soft highlight across the glass. Real windows are scratched
            acrylic and never perfectly clear. */}
        <path
          className={s.glare}
          d="M52 120 Q 110 60, 168 96 L 168 70 Q 110 36, 52 92 Z"
          fill="#ffffff"
          opacity="0.14"
        />
      </svg>
    </div>
  );
}

/**
 * A slow bank of cloud.
 *
 * Two layers at different speeds, which is the whole trick: parallax is
 * what the eye reads as distance, and one layer on its own just looks like
 * a sliding picture.
 */
export function Clouds({ className = "", style }: Decoration) {
  return (
    <div className={`${s.clouds} ${className}`} style={style} aria-hidden>
      <svg viewBox="0 0 1200 220" className={s.cloudSvg} preserveAspectRatio="none">
        <g className={s.cloudFar} fill="currentColor" opacity="0.45">
          <Puff x={120} y={130} r={44} />
          <Puff x={520} y={104} r={54} />
          <Puff x={940} y={138} r={40} />
          <Puff x={1320} y={130} r={44} />
          <Puff x={1720} y={104} r={54} />
        </g>
        <g className={s.cloudNear} fill="currentColor" opacity="0.7">
          <Puff x={300} y={168} r={62} />
          <Puff x={820} y={182} r={72} />
          <Puff x={1500} y={168} r={62} />
          <Puff x={2020} y={182} r={72} />
        </g>
      </svg>
    </div>
  );
}

/** One cloud: three overlapping circles and a flat base, which is all a
    cloud needs to be at this size. */
function Puff({ x, y, r }: { x: number; y: number; r: number }) {
  return (
    <g>
      <circle cx={x} cy={y} r={r} />
      <circle cx={x + r * 0.85} cy={y + r * 0.2} r={r * 0.72} />
      <circle cx={x - r * 0.8} cy={y + r * 0.26} r={r * 0.6} />
      <rect x={x - r * 1.4} y={y} width={r * 2.4} height={r} />
    </g>
  );
}

/**
 * Two aircraft crossing, high up, trailing vapour.
 *
 * The contrail is a dashed line whose dash offset animates, so it appears
 * to be drawn behind the aircraft rather than simply existing. One line of
 * CSS doing the work of a particle system.
 */
export function Contrails({ className = "", style }: Decoration) {
  return (
    <div className={`${s.trails} ${className}`} style={style} aria-hidden>
      <svg viewBox="0 0 1200 320" className={s.trailSvg} preserveAspectRatio="none">
        <g className={s.trailOne}>
          <path
            className={s.trailLine}
            d="M -60 250 C 300 210, 700 150, 1260 70"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
          />
          <g
            className={s.jet}
            style={{
              offsetPath:
                'path("M -60 250 C 300 210, 700 150, 1260 70")',
            }}
          >
            <Jet />
          </g>
        </g>

        <g className={s.trailTwo}>
          <path
            className={s.trailLine}
            d="M -60 110 C 340 150, 760 190, 1260 200"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
          />
          <g
            className={s.jet}
            style={{
              offsetPath:
                'path("M -60 110 C 340 150, 760 190, 1260 200")',
            }}
          >
            <Jet small />
          </g>
        </g>
      </svg>
    </div>
  );
}

/** A silhouette, pointing along its path -- `offsetRotate: auto` in the
    stylesheet turns it, so it is drawn nose-right at the origin. */
function Jet({ small = false }: { small?: boolean }) {
  const k = small ? 0.68 : 1;
  return (
    <path
      transform={`scale(${k})`}
      d="M 14 0 L -4 -5 L -4 -1.6 L -9 -1.6 L -11 -6 L -13 -6 L -12 -1.4 L -15 0 L -12 1.4 L -13 6 L -11 6 L -9 1.6 L -4 1.6 L -4 5 Z"
      fill="currentColor"
    />
  );
}
