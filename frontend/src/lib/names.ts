/**
 * Hebrew names for the airports and airlines Israelis actually fly.
 *
 * NOT a translation table for the world: there are four thousand airports in
 * airports.csv and naming them all in Hebrew is a data project, not a UI
 * concern. An unknown code falls back to the code itself, which is what is
 * printed on a boarding pass and is never wrong.
 *
 * Shared, because the board and the flight-confirmation card must agree. When
 * this lived inside the board, the confirmation step would have shown "HER"
 * beside a row saying "הרקליון" -- the same flight, named two ways, on two
 * screens a customer sees thirty seconds apart.
 */

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

export const cityName = (code: string | null | undefined) =>
  code ? (CITY[code] ?? code) : "";
export const airlineName = (code: string | null | undefined) =>
  code ? (AIRLINE[code] ?? code) : "";

