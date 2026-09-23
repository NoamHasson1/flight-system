/**
 * The dashed arc and the little aeroplane travelling it.
 *
 * Decoration, and marked as such: aria-hidden, pointer-events off, and behind
 * everything. It says nothing that the text does not, so a screen reader is
 * told to ignore it entirely rather than announce a graphic.
 *
 * A server component -- it is static SVG and two CSS animations, so there is
 * no reason for it to cost a byte of JavaScript.
 */
export function FlightPath({ className = "" }: { className?: string }) {
  return (
    <div className={`path ${className}`} aria-hidden>
      <svg
        viewBox="0 0 1200 600"
        preserveAspectRatio="none"
        className="absolute inset-0 size-full"
      >
        <path
          className="pathLine"
          d="M -40 430 C 220 250, 420 180, 700 210 S 1080 330, 1260 180"
        />
      </svg>
      <svg viewBox="0 0 1200 600" className="absolute inset-0 size-full">
        <g
          className="pathPlane"
          style={{
            offsetPath:
              'path("M -40 430 C 220 250, 420 180, 700 210 S 1080 330, 1260 180")',
          }}
        >
          <path
            d="M0 0 l14 5 l-14 5 l3 -5 Z"
            transform="translate(-7,-5)"
          />
        </g>
      </svg>
    </div>
  );
}
