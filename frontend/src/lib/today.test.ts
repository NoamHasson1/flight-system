/**
 * What day it is at Ben Gurion.
 *
 * WHY THESE TESTS AND NOT OTHERS
 *
 * The bug that prompted this module -- a build-time date frozen into a
 * static page -- cannot be caught here, because it is a property of HOW the
 * page renders, not of what this function returns. That one is fixed by the
 * `force-dynamic` export on the landing page, and the honest thing is to say
 * so rather than write a test that looks like it covers it.
 *
 * What these cover is the half that IS a function: the airport's day is not
 * UTC's day and not the viewer's day, and the two disagree for several hours
 * of every single day. Each case below is a real moment when a passenger
 * would have been refused a date they were entitled to check, or offered one
 * that has not happened yet.
 */

import { describe, expect, it } from "vitest";

import { airportToday } from "@/lib/today";

describe("airportToday", () => {
  it("returns the airport's date, not UTC's, late on an Israeli evening", () => {
    /**
     * 22:30 in Israel on 2 October is 19:30 UTC the same day -- fine. An
     * hour and a half later it is not: 00:30 on the 3rd in Israel is still
     * 21:30 on the 2nd in UTC.
     *
     * Somebody whose flight landed twenty minutes ago would have been told
     * their date was in the future, by a form that had already decided the
     * day ended three hours early.
     */
    const justAfterMidnightInIsrael = new Date("2026-10-02T21:30:00Z");

    expect(airportToday(justAfterMidnightInIsrael)).toBe("2026-10-03");
  });

  it("does not run ahead of the airport for a viewer in a later timezone", () => {
    /**
     * The mirror failure, and the one that produces a wrong answer rather
     * than a refusal. At 08:00 UTC on 2 October it is 11:00 in Israel and
     * already 19:00 in Sydney -- but the airport's day is the 2nd, and a
     * Sydney viewer must not be offered the 3rd.
     *
     * This is why the timezone is pinned to the airport instead of read
     * from the machine: the function must give the same answer in Tel Aviv,
     * on a Render container in Frankfurt, and in a browser in Australia.
     */
    const middayIsrael = new Date("2026-10-02T08:00:00Z");

    expect(airportToday(middayIsrael)).toBe("2026-10-02");
  });

  it("formats as YYYY-MM-DD, which is what an input's max attribute needs", () => {
    /**
     * The format is load-bearing, not cosmetic. `<input type="date">`
     * silently IGNORES a `max` it cannot parse -- no error, no warning, the
     * cap simply stops existing. A locale that renders 02/10/2026 would
     * disable the limit altogether and look like it worked.
     */
    expect(airportToday(new Date("2026-10-02T08:00:00Z"))).toMatch(
      /^\d{4}-\d{2}-\d{2}$/,
    );
  });

  it("pads single-digit months and days", () => {
    /**
     * String comparison is how the form validates -- `flightDate > today` --
     * so an unpadded "2026-1-5" would sort after "2026-10-02" and let a
     * January date through as though it were in the future.
     */
    expect(airportToday(new Date("2026-01-05T08:00:00Z"))).toBe("2026-01-05");
  });

  it("tracks the Israeli daylight-saving change rather than a fixed offset", () => {
    /**
     * Israel is UTC+3 in summer and UTC+2 in winter, and the clocks go back
     * in late October. A hardcoded +3 would be wrong for four months of the
     * year -- right through the winter delay season.
     *
     * 22:30 UTC on 1 December is 00:30 on 2 December in Israel (+2). Had
     * the offset been frozen at +3, this would still say the 2nd and pass
     * for the wrong reason; at 21:30 UTC it would not.
     */
    expect(airportToday(new Date("2026-12-01T22:30:00Z"))).toBe("2026-12-02");
    expect(airportToday(new Date("2026-12-01T21:30:00Z"))).toBe("2026-12-01");
  });
});
