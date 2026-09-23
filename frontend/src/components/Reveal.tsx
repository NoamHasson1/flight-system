"use client";

import { useEffect } from "react";

/**
 * Turns on the scroll-reveal animation, once, for the whole page.
 *
 * WHY AN OBSERVER AND NOT A SCROLL HANDLER
 * ----------------------------------------
 * A scroll listener runs on every frame of every scroll for the life of the
 * page, on the main thread, competing with the thing it is trying to animate.
 * An IntersectionObserver is told once what to watch and fires off the main
 * thread when it matters. On a long landing page the difference is the
 * difference between smooth and nearly smooth, and nearly smooth is what
 * people mean when they say a site feels cheap.
 *
 * WHY IT UNOBSERVES
 * -----------------
 * An element that has arrived is finished. Leaving it observed means it
 * re-animates every time it scrolls back into view, which turns a page into
 * a slideshow the second somebody scrolls up to re-read something.
 *
 * WHY IT IS A COMPONENT AND NOT A HOOK PER SECTION
 * ------------------------------------------------
 * So the sections stay SERVER components. They mark themselves with
 * `data-reveal` in HTML, this one client island wires them up, and none of
 * the content waits for JavaScript to exist -- it is visible in the markup
 * whether or not this ever runs.
 */
export function Reveal() {
  useEffect(() => {
    const targets = document.querySelectorAll<HTMLElement>("[data-reveal]");

    // No observer, or motion is unwanted: show everything immediately. The
    // failure mode to avoid is a page whose content is invisible because an
    // animation never ran.
    const wants =
      typeof IntersectionObserver !== "undefined" &&
      !window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    if (!wants) {
      targets.forEach((el) => el.setAttribute("data-shown", "true"));
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          entry.target.setAttribute("data-shown", "true");
          observer.unobserve(entry.target);
        }
      },
      {
        // Fire a little BEFORE the element reaches the viewport edge, so the
        // reveal is finishing as it arrives rather than starting. Catching
        // an animation mid-flight is what makes it look like a page loading
        // rather than a page moving.
        rootMargin: "0px 0px -12% 0px",
        threshold: 0.08,
      },
    );

    targets.forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, []);

  return null;
}
