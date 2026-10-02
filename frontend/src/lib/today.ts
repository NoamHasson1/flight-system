/**
 * What day it is at Ben Gurion.
 *
 * TWO BUGS LIVE HERE, AND BOTH HAVE BITTEN.
 *
 * THE CLOCK MUST NOT BE READ DURING A PRERENDER. The check form capped its
 * date input at `new Date()`, computed while rendering. The landing page is
 * a server component with no `dynamic` export, so Next prerendered it AT
 * BUILD TIME and baked the build date into the HTML as `max="2026-09-27"`.
 * Five days later the date picker still refused October, and it would have
 * refused every day for the life of that build.
 *
 * Hydration does not save it. React does not repair attribute mismatches on
 * hydrating -- it trusts the server HTML -- so the browser kept a clamp the
 * client-side code had already recomputed correctly. Nothing warned. The
 * form's own validation was fine the whole time, because that runs on a
 * later render; only the attribute was frozen.
 *
 * The fix is at the page: anything whose output depends on the clock is
 * `force-dynamic`, so the HTML is built per request. This module exists so
 * there is one place to find that reasoning, and one place to get the date.
 *
 * UTC IS NOT THE AIRPORT'S DAY. `toISOString()` is UTC, and Israel runs
 * UTC+2 or +3. Between 21:00 and midnight Israeli time, UTC still says
 * yesterday -- so somebody checking a flight that landed an hour ago would
 * be told their date is in the future and refused. The reverse is worse for
 * a visitor in Sydney, where UTC is already tomorrow for most of the
 * evening: the form would accept a date Ben Gurion has not reached.
 *
 * The airport's day is the only one that matters, so it is the one we ask
 * for, wherever the viewer happens to be.
 */

const AIRPORT_TIMEZONE = "Asia/Jerusalem";

/**
 * Today at Ben Gurion, as `YYYY-MM-DD`.
 *
 * `en-CA` is the shortest honest way to get ISO order out of Intl; building
 * the string from `getFullYear()` and friends would read the machine's own
 * timezone again and undo the point.
 */
export function airportToday(now: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: AIRPORT_TIMEZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(now);
}
