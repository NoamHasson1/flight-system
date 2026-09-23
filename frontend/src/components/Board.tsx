"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { strings } from "@/lib/strings";

import s from "./hero.module.css";

/**
 * The board of recently disrupted flights.
 *
 * WHY THIS IS THE MOST IMPORTANT SECTION ON THE PAGE
 * --------------------------------------------------
 * Everything else here is an argument. This is evidence. A visitor who finds
 * their own cancelled flight listed and priced, before typing anything, does
 * not need to be persuaded the service works.
 *
 * And it is REAL. Every row comes from `flight_lookups` -- the Ben Gurion
 * board, written into our own archive every fifteen minutes by a cron that
 * does not sleep. No API call, no quota, no hand-written table of
 * plausible-looking flights. That is why this page carries no "for
 * illustration only" line: it has nothing to disclaim.
 *
 * FAILURE IS SILENT, ON PURPOSE
 * -----------------------------
 * If the endpoint is unreachable the section renders nothing at all rather
 * than an error. This is marketing furniture on a landing page, not the
 * customer's answer about their flight -- and a red box on a shop window
 * costs more trust than an absent section costs information. The check form
 * above it still works, which is the thing that matters.
 */

type Row = {
  flight_number: string;
  flight_date: string;
  origin: string;
  destination: string;
  airline: string;
  status: "CANCELLED" | "DELAYED";
  delay_hours: number | null;
  verdict: string;
  amount: string | null;
};

type Board = { updated_at: string; days: number; rows: Row[] };

/**
 * Hebrew names for the airports Israelis actually fly to.
 *
 * NOT a translation table for every airport in the world -- there are four
 * thousand in airports.csv and naming them all in Hebrew is a data project,
 * not a landing page. An unknown code falls back to the code itself, which is
 * what appears on a boarding pass and is never wrong.
 */
const CITY: Record<string, string> = {
  TLV: "תל אביב", LHR: "לונדון", LGW: "לונדון", LTN: "לונדון",
  CDG: "פריז", ORY: "פריז", FCO: "רומא", MXP: "מילאנו", VCE: "ונציה",
  ATH: "אתונה", HER: "הרקליון", RHO: "רודוס", SKG: "סלוניקי", CFU: "קורפו",
  LCA: "לרנקה", PFO: "פאפוס", AYT: "אנטליה", IST: "איסטנבול", SAW: "איסטנבול",
  BER: "ברלין", MUC: "מינכן", FRA: "פרנקפורט", AMS: "אמסטרדם", BRU: "בריסל",
  BCN: "ברצלונה", MAD: "מדריד", LIS: "ליסבון", OTP: "בוקרשט", BUD: "בודפשט",
  PRG: "פראג", WAW: "ורשה", KRK: "קרקוב", VIE: "וינה", ZRH: "ציריך",
  GVA: "ז׳נבה", CPH: "קופנהגן", ARN: "שטוקהולם", OSL: "אוסלו", HEL: "הלסינקי",
  SOF: "סופיה", VAR: "ורנה", BOJ: "בורגס", TBS: "טביליסי", EVN: "ירוואן",
  BAK: "באקו", GYD: "באקו", DXB: "דובאי", AUH: "אבו דאבי", AMM: "עמאן",
  JFK: "ניו יורק", EWR: "ניו יורק", LAX: "לוס אנג׳לס", MIA: "מיאמי",
  BOS: "בוסטון", YYZ: "טורונטו", BKK: "בנגקוק", NRT: "טוקיו", HND: "טוקיו",
  DEL: "דלהי", BOM: "מומבאי", JNB: "יוהנסבורג", ADD: "אדיס אבבה",
  SEZ: "סיישל", MLE: "מלדיביים", TIA: "טירנה", SJJ: "סרייבו", ZAG: "זאגרב",
  SPU: "ספליט", DBV: "דוברובניק", NAP: "נאפולי", CTA: "קטניה", PMO: "פלרמו",
  AER: "סוצ׳י", VRN: "ורונה", STN: "לונדון", BGY: "מילאנו", TSR: "טימישוארה",
  CLJ: "קלוז׳", IAS: "יאשי", KIV: "קישינב", ODS: "אודסה", KBP: "קייב",
  LWO: "לבוב", RIX: "ריגה", VNO: "וילנה", TLL: "טאלין", GOT: "גטבורג",
  BLL: "בילונד", TRN: "טורינו", BLQ: "בולוניה", FLR: "פירנצה", PSA: "פיזה",
  BRI: "בארי", AHO: "אלגרו", OLB: "אולביה", IBZ: "איביזה", AGP: "מלאגה",
  ALC: "אליקנטה", VLC: "ולנסיה", SVQ: "סביליה", OPO: "פורטו", FAO: "פארו",
  TFS: "טנריף", LPA: "לאס פלמאס", FUE: "פוארטבנטורה", ACE: "לנסרוטה",
  CHQ: "חאניה", KGS: "קוס", JTR: "סנטוריני", JMK: "מיקונוס", ZTH: "זקינתוס",
  EFL: "קפלוניה", PVK: "פרבזה", KVA: "קוואלה", VOL: "וולוס", MJT: "מיטילני",
  SMI: "סאמוס", GPA: "פטרה", ADB: "איזמיר", BJV: "בודרום", DLM: "דאלמאן",
  ESB: "אנקרה", TZX: "טרבזון", EVN_: "ירוואן", KUT: "קוטאיסי", BUS: "בטומי",
  NQZ: "אסטנה", ALA: "אלמטי", TAS: "טשקנט", FRU: "בישקק", DYU: "דושנבה",
  SSH: "שארם א-שיח", HRG: "הורגדה", RMF: "מרסא עלם", CAI: "קהיר",
  MCT: "מוסקט", BAH: "בחריין", DOH: "דוחה", KWI: "כווית", RUH: "ריאד",
  JED: "ג׳דה", CMB: "קולומבו", KTM: "קטמנדו", HKT: "פוקט", USM: "קו סמוי",
  DPS: "באלי", SIN: "סינגפור", HKG: "הונג קונג", ICN: "סיאול", PVG: "שנגחאי",
  PEK: "בייג׳ינג", CAN: "גואנגג׳ואו", MEL: "מלבורן", SYD: "סידני",
  ORD: "שיקגו", SFO: "סן פרנסיסקו", LAS: "לאס וגאס", ATL: "אטלנטה",
  IAD: "וושינגטון", PHL: "פילדלפיה", FLL: "פורט לודרדייל", MCO: "אורלנדו",
  YUL: "מונטריאול", MEX: "מקסיקו סיטי", GRU: "סאו פאולו", EZE: "בואנוס איירס",
  LIM: "לימה", BOG: "בוגוטה", NBO: "ניירובי", MBA: "ממבסה", ZNZ: "זנזיבר",
  CPT: "קייפטאון", TNR: "אנטננריבו", MRU: "מאוריציוס",
};

/** Airlines by IATA code. Same rule: the common ones, code as fallback. */
const AIRLINE: Record<string, string> = {
  LY: "אל על", IZ: "אררקיס", "6H": "ישראייר", A4: "ישראייר",
  BZ: "בלו בירד", W6: "ויז אייר", U8: "ויז אייר", FR: "ריינאייר",
  TK: "טורקיש", BA: "בריטיש איירווייז", AF: "אייר פראנס", LH: "לופטהנזה",
  KL: "KLM", SN: "בריסלס", OS: "אוסטריאן", LX: "סוויס", AZ: "ITA",
  VY: "וואלינג", IB: "איבריה", TP: "TAP", SU: "אירופלוט", A3: "אג׳יאן",
  OA: "אולימפיק", RO: "טארום", W4: "ויז אייר", UA: "יונייטד",
  DL: "דלתא", AA: "אמריקן", AC: "אייר קנדה", EK: "אמירייטס",
  ET: "אתיופיאן", MS: "מצרים", RJ: "רויאל ג׳ורדניאן", PC: "פגסוס",
  WZ: "רד ווינגס", S7: "S7", N4: "נורדוויד", UT: "יוטאייר", DP: "פובדה",
  HY: "אוזבקיסטן", KC: "אייר אסטנה", J2: "אזרבייג׳ן", QR: "קטאר",
  FZ: "פליי דובאי", G9: "אראביה", XY: "פלייננס", SV: "סעודיה",
  WY: "עומאן", GF: "גאלף אייר", KU: "כווית", LO: "לוט", OK: "צ׳כיה",
  BT: "אייר בולטיק", DY: "נורוויג׳ן", D8: "נורוויג׳ן", SK: "SAS",
  AY: "פינאייר", EW: "יורוווינגס", X3: "TUI", DE: "קונדור",
  V7: "וולוטאה", TO: "טרנסוויה", HV: "טרנסוויה", U2: "איזיג׳ט",
  EJU: "איזיג׳ט", LS: "ג׳ט2", BY: "TUI", MT: "TUI", ZB: "אייר אלבניה",
  "2L": "הלבטיק", GQ: "סקיי אקספרס", A4_: "אררקיס", H4: "HiSky",
};

const city = (code: string) => CITY[code] ?? code;
const airline = (code: string) => AIRLINE[code] ?? code;

export function FlightBoard() {
  const [board, setBoard] = useState<Board | null>(null);
  const [filter, setFilter] = useState<"all" | "today" | "week">("all");
  const [query, setQuery] = useState("");

  useEffect(() => {
    let live = true;
    // 14 days covers the widest filter, so changing the filter never costs
    // another request -- the whole set is already here and filtering is a
    // client-side slice.
    fetch("/api/v1/disruptions?days=14", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => live && setBoard(data))
      .catch(() => {
        /* Silent. See the note at the top of this file. */
      });
    return () => {
      live = false;
    };
  }, []);

  const scroller = useRef<HTMLDivElement>(null);
  const [paused, setPaused] = useState(false);

  /**
   * The board scrolls itself, slowly, and stops when touched.
   *
   * WHY IT MOVES AT ALL
   * -------------------
   * A static table of cancellations is a table. A moving one is a departures
   * board, which is the object this is imitating and the reason a visitor
   * believes it is live. It is also the only honest way to show sixty rows in
   * the height of twelve.
   *
   * ONE PIXEL AT A TIME, NOT A SCROLL ANIMATION
   * -------------------------------------------
   * `scrollTop += 0.4` on every frame, via requestAnimationFrame, which is
   * the display's own clock. A CSS transform marquee would be smoother still
   * but cannot be grabbed: the moment somebody reaches for their own flight
   * the element is mid-transition and their scroll fights it.
   *
   * IT MUST YIELD IMMEDIATELY
   * -------------------------
   * Pointer in, or keyboard focus inside: it stops. Anything that keeps
   * moving while somebody is trying to read it is not a nice touch, it is an
   * interface refusing to be used. It resumes when they leave.
   *
   * AND IT LOOPS
   * ------------
   * At the bottom it returns to the top. Not a jump -- `behavior: smooth`, so
   * the return reads as the board cycling rather than as a glitch.
   */
  useEffect(() => {
    const el = scroller.current;
    if (!el || paused) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    let frame = 0;
    let resting = 0;

    const step = () => {
      frame = requestAnimationFrame(step);
      // A short pause at the top before setting off, so the first rows can
      // actually be read.
      if (resting > 0) {
        resting -= 1;
        return;
      }
      const atBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 1;
      if (atBottom) {
        el.scrollTo({ top: 0, behavior: "smooth" });
        resting = 180;
        return;
      }
      el.scrollTop += 0.4;
    };

    resting = 150;
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [paused, board]);

  const rows = useMemo(() => {
    if (!board) return [];
    /**
     * "Today" is measured from the BOARD's clock, not the browser's.
     *
     * Two reasons, and the second is the one that matters. A memo that reads
     * Date.now() is impure -- React may re-run it at any time and get a
     * different answer for the same inputs. And a visitor in another
     * timezone has a different idea of today than Ben Gurion does, so
     * filtering on their clock would hide this morning's cancellations from
     * somebody in New York looking for exactly those.
     */
    const asOf = Date.parse(board.updated_at);
    const today = new Date(asOf).toISOString().slice(0, 10);
    const weekAgo = new Date(asOf - 7 * 864e5).toISOString().slice(0, 10);
    const needle = query.trim().toUpperCase();

    return board.rows.filter((r) => {
      if (filter === "today" && r.flight_date !== today) return false;
      if (filter === "week" && r.flight_date < weekAgo) return false;
      if (!needle) return true;
      return (
        r.flight_number.includes(needle) ||
        r.origin.includes(needle) ||
        r.destination.includes(needle) ||
        city(r.destination).includes(query.trim()) ||
        airline(r.airline).includes(query.trim())
      );
    });
  }, [board, filter, query]);

  // Nothing to show and nothing to apologise for.
  if (!board || board.rows.length === 0) return null;

  const b = strings.board;

  return (
    <section id="board" className={`${s.board} px-5 py-20 sm:px-8 sm:py-24`}>
      <div className="mx-auto max-w-6xl">
        <div className="flex flex-wrap items-end justify-between gap-6">
          <div>
            <h2 className="text-title">{b.title}</h2>
            <p className="mt-2 text-body" style={{ color: "var(--text-on-ink-dim)" }}>
              {b.lead}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <span className={s.live}>{b.live}</span>
            <span className="text-caption" style={{ color: "var(--text-on-ink-dim)" }}>
              {b.updated} {relative(board.updated_at)}
            </span>
          </div>
        </div>

        <div className="mt-8 flex flex-wrap items-center justify-between gap-4">
          <div className="flex gap-2">
            {(["all", "today", "week"] as const).map((key) => (
              <button
                key={key}
                type="button"
                onClick={() => setFilter(key)}
                className={`${s.chip} ${filter === key ? s.chipOn : ""}`}
              >
                {b.filters[key]}
              </button>
            ))}
          </div>
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={b.search}
            aria-label={b.search}
            className="w-full rounded-full px-5 py-2.5 text-callout sm:w-80"
            style={{
              background: "rgb(255 255 255 / 0.06)",
              border: "1px solid rgb(255 255 255 / 0.12)",
              color: "var(--text-on-ink)",
            }}
          />
        </div>

        <div
          ref={scroller}
          className={`${s.boardScroll} mt-6`}
          onMouseEnter={() => setPaused(true)}
          onMouseLeave={() => setPaused(false)}
          onFocusCapture={() => setPaused(true)}
          onBlurCapture={() => setPaused(false)}
          onTouchStart={() => setPaused(true)}
          tabIndex={0}
          role="region"
          aria-label={b.title}
        >
          <table className={s.boardTable}>
            <thead>
              <tr>
                <th>{b.columns.flight}</th>
                <th>{b.columns.route}</th>
                <th>{b.columns.airline}</th>
                <th>{b.columns.date}</th>
                <th>{b.columns.status}</th>
                <th>{b.columns.award}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={`${r.flight_number}-${r.flight_date}`}>
                  <td>
                    <span className={`${s.code} font-bold`}>{r.flight_number}</span>
                  </td>
                  <td style={{ color: "var(--text-on-ink-dim)" }}>
                    {city(r.origin)} ← {city(r.destination)}
                  </td>
                  <td style={{ color: "var(--text-on-ink-dim)" }}>{airline(r.airline)}</td>
                  <td>
                    <span className={s.code} style={{ color: "var(--text-on-ink-dim)" }}>
                      {r.flight_date.slice(8, 10)}/{r.flight_date.slice(5, 7)}
                    </span>
                  </td>
                  <td>
                    <Status row={r} />
                  </td>
                  <td>
                    {r.amount ? (
                      <span style={{ color: "var(--color-teal-400)", fontWeight: 700 }}>
                        {b.upTo}{" "}
                        <span className={s.code}>{r.amount}</span>
                      </span>
                    ) : (
                      <span style={{ color: "var(--text-on-ink-dim)" }}>{b.needsCheck}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {rows.length === 0 ? (
            <p className="py-10 text-center text-callout" style={{ color: "var(--text-on-ink-dim)" }}>
              {b.empty}
            </p>
          ) : null}
        </div>

        <p className="mt-5 text-caption" style={{ color: "var(--text-on-ink-dim)" }}>
          {b.footnote}
        </p>
      </div>
    </section>
  );
}

function Status({ row }: { row: Row }) {
  const b = strings.board;
  if (row.status === "CANCELLED") {
    return (
      <span style={{ color: "#f2564d", fontWeight: 700 }}>{b.status.cancelled}</span>
    );
  }
  const hours = row.delay_hours ?? 0;
  const h = Math.floor(hours);
  const m = Math.round((hours - h) * 60);
  return (
    <span style={{ color: "#e8b339", fontWeight: 700 }}>
      {b.status.delayed}{" "}
      <span className={s.code}>
        {h}:{String(m).padStart(2, "0")}
      </span>
    </span>
  );
}

/** "לפני 3 דקות". Rounded, because precision here is noise. */
function relative(iso: string): string {
  const minutes = Math.max(0, Math.round((Date.now() - Date.parse(iso)) / 60000));
  if (minutes < 1) return "עכשיו";
  if (minutes < 60) return `לפני ${minutes} דקות`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `לפני ${hours} שעות`;
  return `לפני ${Math.round(hours / 24)} ימים`;
}
