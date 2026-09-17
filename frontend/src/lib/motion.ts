/**
 * Motion presets.
 *
 * Springs, not durations, for anything a person can touch. A fixed-duration
 * animation cannot respond to new input: grab a closing sheet halfway and a
 * keyframe animation finishes closing before it reopens, which is the exact
 * moment an interface stops feeling like an object and starts feeling like a
 * computer. A spring just gets a new target and stays continuous.
 *
 * Two parameters, not three. Apple deliberately replaced mass/stiffness/damping
 * with damping ratio and response, because those are the two a designer can
 * actually reason about, and Motion's `bounce` + `duration` map onto them
 * closely enough to think in the same terms.
 *
 *   damping 1.0  -> bounce 0     critically damped, settles without overshoot
 *   damping 0.8  -> bounce 0.2   a little overshoot
 *
 * The rule for which to use: **bounce only when the gesture itself carried
 * momentum.** Overshoot on a menu that simply faded in feels like a toy.
 * Overshoot on a card you flicked feels like the card has mass.
 */

import type { Transition } from "motion/react";

/** No overshoot. The default for everything that is not thrown. */
export const spring: Transition = {
  type: "spring",
  bounce: 0,
  duration: 0.4,
};

/** Snappier, still no overshoot. Small elements, quick state changes. */
export const springQuick: Transition = {
  type: "spring",
  bounce: 0,
  duration: 0.28,
};

/**
 * Sheets and drawers. Apple ships damping 0.8 / response 0.3 here, and the
 * bounce is earned: a sheet is dragged, so it arrives carrying momentum.
 */
export const springSheet: Transition = {
  type: "spring",
  bounce: 0.2,
  duration: 0.32,
};

/** Released after a drag or a flick. The only place real bounce belongs. */
export const springMomentum: Transition = {
  type: "spring",
  bounce: 0.25,
  duration: 0.4,
};

/**
 * Project where a flick is going, then snap to the target nearest that point.
 *
 * Snapping to the nearest boundary from the RELEASE point makes a flick feel
 * like a nudge. Projecting momentum first is what makes it feel thrown.
 *
 * This is the exponential-decay form Apple ships, not the textbook
 * v²/(2·deceleration) — they are not the same curve and the difference is
 * visible.
 *
 * @param velocity px/s at the moment of release
 * @param decelerationRate 0.998 for normal scroll feel, 0.99 for snappier
 */
export function projectMomentum(velocity: number, decelerationRate = 0.998): number {
  return ((velocity / 1000) * decelerationRate) / (1 - decelerationRate);
}

/**
 * Progressive resistance past a boundary.
 *
 * A hard stop reads as frozen — the user wonders whether the app has hung.
 * Resistance that grows the further you push reads as "responsive, but there
 * is nothing more here", which is the truth.
 */
export function rubberband(
  overshoot: number,
  dimension: number,
  constant = 0.55,
): number {
  return (
    (overshoot * dimension * constant) /
    (dimension + constant * Math.abs(overshoot))
  );
}

/**
 * Whether this person has asked for less motion.
 *
 * Checked at the point of animating rather than once at module load, because
 * the preference can change while the page is open.
 */
export function prefersReducedMotion(): boolean {
  if (typeof window === "undefined") return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/**
 * The same transition, degraded for reduced motion.
 *
 * Reduced motion does not mean no feedback. It means a gentler, non-vestibular
 * equivalent: the element still appears, it just cross-fades instead of
 * travelling. Removing the feedback entirely would leave the interface
 * changing with no explanation of what changed.
 */
export function respectMotion(transition: Transition): Transition {
  if (!prefersReducedMotion()) return transition;
  return { duration: 0.18, ease: "easeOut" };
}

/**
 * Enter and exit along the same path.
 *
 * If something leaves downward it must have arrived from below. In-from-the-
 * right and out-the-bottom reads as two unrelated events and quietly costs the
 * user their sense of where things are.
 */
export const enterFromBelow = {
  initial: { opacity: 0, y: 12 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: 12 },
} as const;

export const enterFromAbove = {
  initial: { opacity: 0, y: -12 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -12 },
} as const;

/**
 * Glass surfaces materialise rather than fade.
 *
 * Animating blur and scale together makes the surface read as a real material
 * arriving. A plain opacity fade on a blurred panel looks like a screenshot
 * being turned up.
 */
export const materialize = {
  initial: { opacity: 0, scale: 0.97, backdropFilter: "blur(0px)" },
  animate: { opacity: 1, scale: 1, backdropFilter: "blur(20px)" },
  exit: { opacity: 0, scale: 0.97, backdropFilter: "blur(0px)" },
} as const;

/** Stagger for a list arriving. Small enough to read as one motion. */
export const stagger = (index: number, step = 0.04) => ({
  ...spring,
  delay: index * step,
});
