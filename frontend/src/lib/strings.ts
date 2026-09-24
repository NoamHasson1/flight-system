/**
 * Every word the customer reads, in one file.
 *
 * WHY HEBREW, AND WHY THE WHOLE FILE
 * ----------------------------------
 * The customers are Israeli passengers, and the lawyer behind the service is
 * an Israeli one. A half-translated product is worse than either language
 * alone: the reader hits an English sentence at the moment they are deciding
 * whether to trust this with a passport number.
 *
 * So the whole flow is Hebrew -- the landing page, the verdict, the claim
 * wizard, the errors -- not just the parts a visitor sees first.
 *
 * KEEPING IT IN ONE FILE
 * ----------------------
 * Tone. This product talks about money and the law at a moment when something
 * has already gone wrong for somebody. Keeping the copy together is the only
 * way to notice that one screen is reassuring and the next sounds like a bank.
 *
 * The rules: plain words over legal ones, never blame the reader, and never
 * claim more certainty than we have.
 *
 * ON NUMBERS AND TESTIMONIALS
 * ---------------------------
 * There are none here yet, deliberately. Figures like "7 million recovered"
 * and named reviews are advertising for a named lawyer, and unverified ones
 * must not ship. The sections that would carry them are built and read
 * correctly without them -- see `credentials` and `testimonials`, both empty.
 * Filling either is a data change, not a layout change.
 */

export const strings = {
  brand: {
    name: "Skyclaim",
    lawyer: "עו״ד יצחק מימון",
    lawyerField: "דיני תעופה וזכויות נוסעים",
    tagline: "חוק שירותי תעופה · EU261 · UK261",
  },

  nav: {
    rights: "הזכויות שלכם",
    calculator: "מחשבון פיצוי",
    board: "לוח שיבושים",
    how: "איך זה עובד",
    faq: "שאלות נפוצות",
    about: "מי אנחנו",
    cta: "בדיקת זכאות",
    aria: "ניווט ראשי",
    menu: "תפריט",
  },

  /**
   * The page that explains the law.
   *
   * WRITTEN FOR SOMEBODY WHOSE FLIGHT WAS JUST CANCELLED, not for a lawyer.
   * Every section answers a question a passenger actually asks, in the order
   * they ask it: does anything cover me, how much, what stops me, how long do
   * I have.
   *
   * THE FIGURES ARE NOT HERE. They come from /api/v1/regulations, which reads
   * them out of the rules engine. Written twice they drift, and a page
   * promising a number the check will not honour is the one inconsistency
   * that makes somebody stop believing the answer.
   */
  rights: {
    eyebrow: "הזכויות שלכם",
    title: "מה מגיע לכם כשטיסה משתבשת",
    lead:
      "שלושה חוקים שונים יכולים לחול על אותה טיסה, ולפעמים יותר מאחד. " +
      "הנה מה שכל אחד מהם אומר — בשפה פשוטה.",

    whichApplies: {
      title: "איזה חוק חל עליי?",
      lead: "לא צריך לדעת. אנחנו בודקים את כולם. אבל אם בא לכם להבין:",
    },

    laws: [
      {
        key: "ISRAEL",
        badge: "ישראל",
        name: "חוק שירותי תעופה",
        alias: 'המוכר כ"חוק טיבי"',
        covers: "כל טיסה שיוצאת מישראל, נוחתת בישראל, או טיסת פנים.",
        detail:
          "החוק הישראלי הוא הרחב ביותר מבחינת נוסעים ישראלים: הוא לא שואל " +
          "מי חברת התעופה ולא מאיפה היא רשומה. אם הטיסה נגעה בישראל — הוא חל.",
        triggers: [
          "ביטול טיסה",
          "עיכוב ארוך בהמראה",
          "סירוב עלייה למטוס (overbooking)",
          "הורדה מדרגת שירות",
        ],
        note:
          "שימו לב: החוק הישראלי סופר את העיכוב בהמראה, לא בנחיתה — וזה " +
          "הבדל מהותי מהחוק האירופי.",
      },
      {
        key: "EC261",
        badge: "אירופה",
        name: "תקנה אירופית 261/2004",
        alias: "EC261",
        covers:
          "כל טיסה שממריאה משדה תעופה באיחוד האירופי, ובנוסף טיסה שנוחתת " +
          "באיחוד כשהמוביל הוא חברה אירופית.",
        detail:
          "לכן טיסה תל אביב–פריז מכוסה כשהיא חוזרת מפריז תמיד, ובכיוון " +
          "השני רק אם חברת התעופה אירופית. אל על בדרך לפריז — לא. אייר " +
          "פראנס באותו מסלול — כן.",
        triggers: [
          "ביטול טיסה",
          "עיכוב ארוך בנחיתה",
          "סירוב עלייה למטוס",
          "קונקשן שהוחמץ באשמת חברת התעופה",
        ],
        note:
          "התקנה האירופית סופרת את העיכוב בנחיתה — כמה מאוחר הגעתם ליעד " +
          "הסופי, ולא מתי המטוס עזב.",
      },
      {
        key: "UK261",
        badge: "בריטניה",
        name: "החוק הבריטי",
        alias: "UK261",
        covers:
          "טיסה שיוצאת מבריטניה, או נוחתת בבריטניה עם חברה בריטית או אירופית.",
        detail:
          "אחרי הברקזיט בריטניה העתיקה את התקנה האירופית לחוק שלה. המבנה " +
          "זהה, הסכומים נקובים בלירות שטרלינג.",
        triggers: ["ביטול טיסה", "עיכוב ארוך בנחיתה", "סירוב עלייה למטוס"],
        note: "",
      },
    ] as const,

    amounts: {
      title: "כמה כסף מדובר",
      lead:
        "הסכום נקבע לפי מרחק הטיסה — לא לפי מחיר הכרטיס. נוסע שקנה כרטיס " +
        "ב-300 ש״ח ונוסע שקנה באלף מקבלים אותו דבר.",
      perPassenger: "לכל נוסע",
      upTo: 'עד {n} ק״מ',
      over: 'מעל {n} ק״מ',
      between: 'ק״מ {a}–{b}',
      threshold: "סף העיכוב",
      measuredDeparture: "נמדד בהמראה",
      measuredArrival: "נמדד בנחיתה",
      hours: "שעות",
      familyNote:
        "הפיצוי הוא לכל נוסע בהזמנה. משפחה של ארבעה מקבלת פי ארבעה.",
      sourceNote:
        "הסכומים כאן נקראים ישירות ממנוע הבדיקה של Skyclaim — אותם מספרים " +
        "בדיוק שהבדיקה שלכם תחזיר.",
    },

    blockers: {
      title: "מה יכול למנוע פיצוי",
      lead:
        "שלושה דברים, וכדאי להכיר אותם — כי חברות התעופה מסתמכות עליהם " +
        "בדיוק כשהם לא באמת חלים.",
      items: [
        {
          title: "נסיבות חריגות",
          body:
            "מזג אוויר קיצוני, שביתת בקרי טיסה, איום ביטחוני, סגירת מרחב " +
            "אווירי. אלה באמת פוטרים את חברת התעופה.",
          caveat:
            "אבל תקלה טכנית במטוס היא כמעט תמיד לא נסיבה חריגה — זו " +
            "אחריות החברה לתחזק את הצי שלה. גם שביתה של עובדי החברה עצמה " +
            "בדרך כלל לא פוטרת אותה.",
        },
        {
          title: "הודעה מראש על ביטול",
          body:
            "אם חברת התעופה הודיעה לכם 14 יום או יותר לפני מועד הטיסה — " +
            "אין פיצוי.",
          caveat:
            "פחות מ-14 יום, ובדרך כלל כן. וזו הסיבה שאנחנו שואלים אתכם " +
            "מתי הודיעו לכם: אף מאגר טיסות בעולם לא יודע את זה. רק אתם.",
        },
        {
          title: "התיישנות",
          body:
            "לכל חוק יש חלון זמן. בישראל — ארבע שנים. בבריטניה — שש. " +
            "באירופה זה משתנה בין מדינה למדינה.",
          caveat:
            "כלומר טיסה מ-2023 עדיין יכולה להיות שווה כסף. שווה לבדוק " +
            "לפני שמוותרים.",
        },
      ] as const,
    },

    alsoOwed: {
      title: "לא רק פיצוי",
      lead:
        "בנוסף לסכום הפיצוי, חברת התעופה חייבת לדאוג לכם בזמן ההמתנה. זה " +
        "נקרא ״זכות לטיפול״ והיא לא תלויה בזכאות לפיצוי.",
      items: [
        "ארוחות ומשקאות בהתאם לזמן ההמתנה",
        "לינה במלון אם נדרשת שהייה לילה",
        "הסעה בין שדה התעופה למלון",
        "שתי שיחות טלפון או הודעות",
        "טיסה חלופית ליעד, או החזר מלא של הכרטיס",
      ] as const,
      receipts:
        "שילמתם מהכיס? שמרו קבלות. החזר הוצאות נתבע בנפרד מהפיצוי, ולעיתים " +
        "מגיע גם כשהפיצוי עצמו לא.",
    },

    cta: {
      title: "לא בטוחים מה חל עליכם?",
      lead: "זה בדיוק מה שהבדיקה עושה. דקה, בחינם, בלי הרשמה.",
      button: "בדיקת זכאות",
    },

    disclaimer:
      "העמוד הזה הוא הסבר כללי ואינו ייעוץ משפטי. הזכאות בפועל תלויה " +
      "בנסיבות הספציפיות של הטיסה שלכם.",
  },

  hero: {
    /* Said once, at the top, because it is the question a visitor actually
       has: whose side is this service on. */
    badge: "אנחנו מייצגים נוסעים בלבד. לא חברות תעופה.",
    headlineA: "הטיסה בוטלה",
    headlineB: "או התעכבה?",
    accent: "בדקו כמה כסף מגיע לכם.",
    subhead:
      "בדיקת זכאות ראשונית תוך פחות מדקה. אנחנו בודקים מה קרה לטיסה בפועל " +
      "ואת הזכויות שעשויות להגיע לכם.",
    cta: "בדיקת זכאות",
    secondaryCta: "לוח שיבושי טיסות",
    cardTitle: "בדיקת זכאות",
    reassurance: "בלי הרשמה · הבדיקה חינם · לוקח דקה",
  },

  check: {
    /* The boarding-pass framing. English on purpose: it is the language of a
       boarding pass, and it is pastiche rather than content -- nobody has to
       read it to use the form. */
    stripBrand: "SKYCLAIM AIR",
    stripSub: "BOARDING PASS · ELIGIBILITY CHECK",
    stripFree: "FREE",
    eyebrow: "בדיקת זכאות — חינם, בלי הרשמה",
    lead: "מזינים את פרטי הטיסה, ומקבלים תשובה תוך דקה.",
    /* Under the form, not over it. Somebody at this point has decided to
       type a flight number; the face is there to reassure, not to sell. */
    backedBy: "הבדיקה נשענת על הידע של",
    backedByLink: "עוד על יצחק",
  },

  form: {
    flightNumberLabel: "מספר טיסה",
    flightNumberPlaceholder: "LY315",
    flightNumberHint: "קוד החברה והמספר, למשל LY315 או BZ734.",
    dateLabel: "תאריך הטיסה",
    dateHint: "היום שבו הטיסה המריאה, לא היום שבו הזמנתם.",
    submit: "בדיקת זכאות",
    submitting: "בודקים את הטיסה…",
    /**
     * Shown once a check has been running long enough to look broken.
     *
     * The check WILL succeed; it is waiting for something slow. Saying so is
     * the difference between a slow answer and a broken site: somebody
     * watching a silent spinner for thirty seconds closes the tab, and a
     * closed tab is a claim nobody ever hears about.
     */
    submittingSlow: "עדיין בודקים — החיפוש הראשון אחרי הפסקה יכול לקחת עד דקה…",
  },

  /**
   * The step between finding a flight and showing what it is worth.
   *
   * WHY IT EXISTS
   * -------------
   * A flight number is reused: LY315 flies most days, and somebody typing
   * the wrong date gets a real flight that is not theirs. Without this they
   * would see a confident verdict about a journey they did not take -- and
   * the dangerous half is a "no" for somebody who is in fact owed money.
   *
   * It also does something quieter. Being shown the route and asked to
   * confirm makes the next screen feel like an answer about YOUR flight
   * rather than a number a website produced.
   */
  confirm: {
    found: "מצאנו את הטיסה",
    question: "זו הטיסה שלכם?",
    yes: "כן, המשך",
    no: "לא, חיפוש מחדש",
    steps: ["בדיקה", "פרטים", "נוסעים", "חתימה"] as const,
  },

  /**
   * Errors the customer can act on.
   *
   * None say "שגיאה" and none blame the reader. Somebody whose flight was
   * cancelled and who is now being told they typed something wrong is having
   * a worse day than whoever wrote the message.
   */
  errors: {
    flightNumberRequired: "הזינו את מספר הטיסה מתוך ההזמנה.",
    flightNumberFormat:
      "זה לא נראה כמו מספר טיסה. בדרך כלל שתי אותיות ואחריהן ספרות, " +
      "למשל LY315.",
    dateRequired: "הזינו את התאריך שבו הטיסה המריאה.",
    emailFormat: "זו לא נראית כמו כתובת אימייל.",
    dateFuture:
      "התאריך הזה בעתיד. הזינו את היום שבו הטיסה המריאה — אפשר לבדוק רק " +
      "טיסות שכבר יצאו.",
    dateTooOld:
      "הטיסה הזו מלפני יותר משש שנים, מעבר לתקופת ההתיישנות בכל אחת " +
      "מהמדינות שאנחנו מכסים.",
    /**
     * The most important string in this file.
     *
     * Somebody who reads "משהו השתבש" and closes the tab has lost a claim
     * nobody will ever know about. It has to say, explicitly, that this is
     * not an answer about their flight.
     */
    unreachable:
      "לא הצלחנו להגיע למאגר הטיסות כרגע. זו תקלה אצלנו והיא לא אומרת " +
      "כלום על הטיסה שלכם — נסו שוב עוד רגע, ואל תניחו שאין לכם תביעה.",
  },

  /**
   * The verdict, in plain words.
   *
   * Deliberately NO regulation names, thresholds or clause-by-clause
   * reasoning: the customer asked a simple question and gets a simple answer.
   * All of that reasoning is still computed and still STORED against the
   * check -- it is what support and the claim handler work from -- it just is
   * not what this screen is for.
   */
  verdict: {
    ELIGIBLE: {
      eyebrow: "חדשות טובות",
      lead: "מגיע לכם פיצוי",
      amountLabel: "לכל נוסע בהזמנה",
    },
    NOT_ELIGIBLE: {
      eyebrow: "נבדק",
      /* Not "מצטערים" and not "לצערנו". This is a finding about an airline's
         obligation, not a rejection of the person reading it. */
      lead: "הטיסה הזו לא עומדת בתנאים",
      body:
        "זה לא קשור לשום דבר שעשיתם. הפיצוי תלוי בכמה הטיסה באמת איחרה " +
        "ובאיזה מסלול היא טסה, והמקרה הזה נופל מחוץ לגבולות האלה.",
      doubt:
        "אם נחתתם מאוחר יותר ממה שמופיע כאן, או שחברת התעופה אמרה לכם משהו " +
        "אחר — בקשו מאיתנו בדיקה ידנית.",
    },
    NEEDS_REVIEW: {
      eyebrow: "עוד דבר אחד",
      /* Never a polite no. It has to be obvious this is unfinished. */
      lead: "צריך שנבדוק את זה ידנית",
      body:
        "משהו בטיסה הזו לא ניתן לבדיקה אוטומטית. זה לא 'לא' — השאירו " +
        "כתובת אימייל ואדם יחזור אליכם.",
    },
    /**
     * The amount is real and the law is settled. One fact is missing, and the
     * person reading this is the only one who has it.
     *
     * Showing the figure is the point. "נבדוק ונחזור אליכם" and "מגיעים לכם
     * 1,530 ש״ח, בכפוף לשאלה אחת" describe the same state of knowledge, and
     * only one of them gets answered.
     */
    LIKELY_ELIGIBLE: {
      eyebrow: "כמעט בוודאות",
      lead: "נראה שמגיע לכם",
      amountLabel: "לכל נוסע, בכפוף לשאלה אחת",
    },
  },

  /**
   * The questions no flight database can answer.
   *
   * Each is keyed to what the backend asked for. The wording lives here and
   * the key lives in the rules, so a law can require an answer without
   * dictating how it is put to somebody.
   */
  questions: {
    cancellation_notice: {
      title: "מתי חברת התעופה הודיעה לכם?",
      /* The law, in one sentence, so the question does not read as an
         obstacle invented by us. */
      explain:
        "הודעה של שבועיים מראש ומעלה פוטרת את חברת התעופה. פחות מזה — " +
        "הפיצוי עומד בתוקפו.",
      options: [
        { value: "NEVER_TOLD", label: "לא הודיעו לי בכלל" },
        { value: "ON_THE_DAY", label: "ביום הטיסה" },
        { value: "UNDER_A_WEEK", label: "פחות משבוע לפני" },
        { value: "ONE_TO_TWO_WEEKS", label: "שבוע עד שבועיים לפני" },
        { value: "OVER_TWO_WEEKS", label: "יותר משבועיים לפני" },
        { value: "CANNOT_REMEMBER", label: "אני לא זוכר" },
      ],
    },
    actual_arrival: {
      title: "מתי נחתתם בפועל?",
      explain:
        "הטיסה שלכם יצאה מאוחר מספיק כדי לזכות בפיצוי בכל מקרה. אם בסוף " +
        "חברת התעופה הביאה אתכם קרוב ללוח הזמנים, הסכום קטן בחצי.",
      options: [] as const,
    },
  },

  result: {
    notFoundLead: "לא מצאנו את הטיסה הזו",
    ambiguousLead: "באיזו טיסה טסתם?",
    searchAgain: "חיפוש טיסה אחרת",
    ambiguousExplain:
      "יותר מטיסה אחת נשאה את המספר הזה באותו תאריך. בחרו את שלכם ונבדוק.",
    yourFlight: "הטיסה שלכם",
    whatNext: "מה קורה עכשיו",
    nextSteps: [
      "מוסיפים את הנוסעים שבהזמנה ומעלים את הכרטיס.",
      "אנחנו פונים לחברת התעופה בכתב, בהסתמך על הסעיף שחל על המקרה.",
      "מקבלים את הכסף. אנחנו גובים עמלה רק אם התביעה מצליחה.",
    ] as const,
    caveat:
      "חברות תעופה לא חייבות לפצות כשהסיבה הייתה מחוץ לשליטתן — מזג אוויר " +
      "קיצוני, למשל. נשאל אתכם מה נאמר לכם.",
    howMany: "כמה נוסעים הייתם בהזמנה?",
    howManyHint: "הפיצוי הוא לכל נוסע, אז זה משנה את הסכום.",
    totalFor: "סה״כ ל-{n} נוסעים",
    startClaim: "התחילו תביעה",
    askHuman: "בקשו בדיקה ידנית",
    checkAnother: "בדקו טיסה נוספת",
  },

  /** The live disruptions board, built from our own archive. */
  board: {
    pageLead:
      "כל טיסה שבוטלה או התעכבה בנתב״ג לאחרונה, עם הפיצוי שעשוי להגיע " +
      "עליה. הנתונים מגיעים מלוח הטיסות הרשמי ומתעדכנים כל רבע שעה.",
    title: "לוח שיבושי טיסות",
    lead: "טיסות שבוטלו או התעכבו לאחרונה מישראל ואליה.",
    live: "LIVE",
    updated: "עודכן",
    filters: { all: "הכול", today: "היום", week: "השבוע" },
    search: "חפשו מספר טיסה, יעד או חברת תעופה",
    columns: {
      flight: "טיסה",
      route: "מסלול",
      airline: "חברה",
      date: "תאריך",
      status: "סטטוס",
      award: "פיצוי אפשרי",
    },
    status: { cancelled: "בוטלה", delayed: "עיכוב" },
    upTo: "עד",
    needsCheck: "בדיקה",
    empty: "לא נרשמו שיבושים בתקופה הזו.",
    /* Ours comes from the archive rather than from a hand-written table, so
       it does not carry the reference site's "for illustration only". It does
       carry this, which is true: a board entry is not a ruling. */
    footnote:
      "הנתונים מגיעים מלוח הטיסות הרשמי של נתב״ג. פיצוי בפועל נקבע לפי " +
      "נסיבות המקרה.",
    checkThis: "בדקו את הטיסה",
  },

  /** What the law pays, by distance. */
  bands: {
    title: "כמה פיצוי יכול להגיע על ביטול טיסה?",
    lead:
      "בחלק מהמקרים גובה הפיצוי נקבע בין היתר לפי מרחק הטיסה. הפיצוי הוא " +
      "לכל נוסע הזכאי לו, ולא לפי מחיר כרטיס הטיסה.",
    familyToggle: "טסים כמשפחה / קבוצה?",
    perPassenger: "לכל נוסע",
    rows: [
      { range: 'עד 2,000 ק״מ', amount: "₪1,530", places: ["לרנקה", "אתונה", "רודוס", "בוקרשט"] },
      { range: 'ק״מ 2,000–4,500', amount: "₪2,450", places: ["רומא", "ברלין", "פריז", "אמסטרדם", "לונדון"] },
      { range: 'מעל 4,500 ק״מ', amount: "₪3,670", places: ["ניו יורק", "בנגקוק", "טוקיו", "טורונטו"] },
    ] as const,
    familyExample: "טסתם כמשפחה של 4? טיסה ארוכה שבוטלה יכולה להגיע לדוגמה ל:",
    familyCaveat: "כפוף כמובן לזכאות ולנסיבות המקרה.",
    cta: "בדקו מה מגיע על הטיסה שלכם",
    updatedNote: "הסכומים מעודכנים לספטמבר 2026.",
  },

  frameworks: {
    title: "אתם לא צריכים לדעת איזה חוק חל על הטיסה שלכם.",
    lead: "Skyclaim בודקת את פרטי המקרה מול המסגרות הרלוונטיות.",
    items: ["חוק שירותי תעופה", "EU261", "UK261", "אמנת מונטריאול"] as const,
  },

  lawyer: {
    eyebrow: "לא רק מערכת. יש מי שעומד מאחוריה.",
    name: "עו״ד יצחק מימון",
    lead: "ניסיון בדיני תעופה, בתוך תהליך הרבה יותר פשוט.",
    body:
      "עו״ד יצחק מימון מתמחה בדיני תעופה ובזכויות נוסעים, ומייצג נוסעים מול " +
      "חברות התעופה — מקומיות ובינלאומיות כאחד. ההיכרות עם המסגרות " +
      "המשפטיות — חוק שירותי תעופה, התקנה האירופית, החוק הבריטי ואמנת " +
      "מונטריאול — היא שעומדת בבסיס הבדיקה של Skyclaim.",
    pullQuoteA: "אנחנו מייצגים נוסעים בלבד.",
    pullQuoteB: "לא חברות תעופה.",
    photoAlt: "עו״ד יצחק מימון",
    /**
     * EMPTY ON PURPOSE, AND NOT A PLACEHOLDER.
     *
     * Years of experience, cases handled, sums recovered, review counts --
     * every one of these is advertising for a named advocate, and publishing
     * an unverified figure is a problem for him, not only for us. The section
     * lays out correctly with none, so adding a verified figure later is a
     * data change and nothing else.
     */
    credentials: [] as readonly { value: string; label: string }[],
  },

  howItWorks: {
    titleA: "אתם נותנים לנו את פרטי הטיסה.",
    titleB: "אנחנו דואגים לשאר.",
    steps: [
      { n: "01", title: "מאתרים את הטיסה", body: "מספר טיסה או חיפוש לפי מסלול." },
      { n: "02", title: "בודקים זכאות", body: "המערכת בודקת את האירוע ואת הזכויות האפשריות." },
      { n: "03", title: "אנחנו מטפלים", body: "אם יש בסיס לתביעה, משלימים פרטים ומכאן אנחנו מול חברת התעופה." },
    ] as const,
    cta: "בדיקת זכאות",
  },

  why: {
    title: "חברת התעופה מכירה את הכללים.",
    lead: "עכשיו גם אתם יכולים לדעת מה מגיע לכם.",
    items: [
      { title: "טכנולוגיה", body: "איתור ובדיקת הטיסה במהירות ובדיוק." },
      { title: "פשטות", body: "תהליך ברור במקום התכתבויות וטפסים." },
      { title: "ניסיון משפטי", body: "עו״ד יצחק מימון וההתמחות בזכויות נוסעים." },
    ] as const,
  },

  /**
   * The Google rating.
   *
   * VERIFIED, unlike the figures still absent from `lawyer.credentials`.
   * Read off the listing for "יצחק מימון עורך דין תעופה" on 24 September
   * 2026: 5.0 from 309 reviews. The link goes to that listing so anybody can
   * check it in one click, which is the whole reason a rating is worth
   * showing at all.
   *
   * The COUNT will drift as reviews arrive. It is written here rather than
   * fetched because fetching it needs the Google Places API and a key, and a
   * number that is a little low is honest while a number that is a little
   * high is not -- so it only ever needs updating upward, at leisure.
   */
  /**
   * The four claims across the top.
   *
   * Two are verified externally: the rating and the review count come from
   * the Google listing and the badge beside them links to it, so anybody can
   * check in one click.
   *
   * Two are the firm's own: the sum recovered and the positioning. They are
   * published on the author's instruction, which is the right way round --
   * they are claims about his practice and his to stand behind, not mine to
   * invent. Kept here rather than inline so revising one is a data change.
   */
  trust: [
    { value: "נוסעים בלבד", label: "מייצגים רק נוסעים", icon: "people" },
    { value: "7+ מיליון ₪", label: "פיצויים שהושגו", icon: "trend" },
    { value: "5.0", label: "דירוג ממוצע בגוגל", icon: "stars" },
    { value: "309", label: "ביקורות Google", icon: "star" },
  ] as const,

  reviews: {
    rating: "5.0",
    count: 309,
    countLabel: "ביקורות בגוגל",
    ratingLabel: "דירוג ממוצע",
    verified: "פרופיל Google מאומת",
    readAll: "לקריאת כל הביקורות בגוגל",
    url:
      "https://www.google.com/maps/place/?q=place_id:" +
      "ChIJ0-AAE2m-gxMRfNCXrJmW_is",
    title: "נוסעים שכבר עברו את זה",
    lead:
      "הדירוג והביקורות מתפרסמים בפרופיל Google של המשרד — לא אצלנו באתר, " +
      "כך שאי אפשר לערוך אותם.",
    /**
     * EMPTY, and not a placeholder.
     *
     * Review text belongs to Google and to the people who wrote it.
     * Republishing it by copying it off the listing is both a terms
     * violation and a thing we could quietly edit -- which is exactly what
     * makes a testimonial on a company's own site worth less than a rating
     * that links out.
     *
     * To fill this properly: the Google Places API returns reviews with
     * attribution, under terms that permit displaying them. Until then the
     * rating and the link do the work honestly.
     */
    quotes: [] as readonly { quote: string; name: string; when: string }[],
  },

  cases: {
    title: "הטיסה השתבשה? ייתכן שמגיע לכם כסף.",
    items: [
      "ביטול טיסה",
      "עיכוב משמעותי",
      "קונקשן שהוחמץ",
      "סירוב עלייה למטוס",
      "הוצאות מלון / אוכל / תחבורה",
      "טיסה חלופית שהגיעה מאוחר",
    ] as const,
    unsure: "לא בטוחים?",
    unsureBody: "פשוט תנו לנו לבדוק.",
  },

  /** The standalone calculator page. */
  calculator: {
    eyebrow: "מחשבון פיצוי",
    title: "כמה כסף מגיע לכם?",
    lead:
      "שלוש שאלות, ותדעו את הסכום. זו הערכה לפי החוק — הבדיקה האמיתית " +
      "מסתכלת על מה קרה לטיסה שלכם בפועל.",
    destination: "לאן טסתם?",
    destinationHint: "המרחק קובע את גובה הפיצוי.",
    whatHappened: "מה קרה?",
    passengers: "כמה נוסעים היו בהזמנה?",
    passengersHint: "הפיצוי הוא לכל נוסע.",
    events: [
      { key: "CANCELLED", label: "הטיסה בוטלה" },
      { key: "DELAYED", label: "הטיסה התעכבה" },
      { key: "DENIED", label: "לא נתנו לי לעלות למטוס" },
    ] as const,
    /**
     * Distances from Ben Gurion, in kilometres, great-circle.
     *
     * The same measure the engine uses, so the calculator and the check land
     * in the same band. A rounded "about 3,000km" would put Rome in the wrong
     * band on a bad day, and a calculator that disagrees with the check is
     * worse than no calculator.
     */
    destinations: [
      { label: "לרנקה / קפריסין", km: 262 },
      { label: "אתונה", km: 1220 },
      { label: "איסטנבול", km: 1135 },
      { label: "רודוס", km: 936 },
      { label: "בוקרשט", km: 1470 },
      { label: "רומא", km: 2280 },
      { label: "ברלין", km: 2870 },
      { label: "פריז", km: 3250 },
      { label: "לונדון", km: 3580 },
      { label: "אמסטרדם", km: 3320 },
      { label: "ניו יורק", km: 9130 },
      { label: "בנגקוק", km: 7110 },
      { label: "טוקיו", km: 9160 },
      { label: "יעד אחר", km: 0 },
    ] as const,
    otherKm: 'מרחק משוער בק״מ',
    result: "ההערכה שלנו",
    perPassenger: "לכל נוסע",
    total: "סה״כ להזמנה",
    under: "לפי",
    nothingYet: "בחרו יעד ומה קרה, ונראה לכם כמה זה שווה.",
    /* Shown for a delay, because the Israeli threshold is eight hours at
       departure and a three-hour delay out of Tel Aviv pays nothing under
       Israeli law while possibly paying under EC261. Saying "it depends on
       how long" up front avoids a number that turns out to be wrong. */
    delayNote:
      "בעיכוב הסכום תלוי גם באורך העיכוב ובאיזה חוק חל — החוק הישראלי סופר " +
      "8 שעות בהמראה, האירופי 3 שעות בנחיתה. הבדיקה תדע לומר בדיוק.",
    caveat:
      "ההערכה מניחה שהשיבוש היה באחריות חברת התעופה ושלא קיבלתם הודעה " +
      "14 יום מראש. הבדיקה בודקת את שני הדברים האלה בפועל.",
    cta: "בדקו את הטיסה שלכם",
  },

  faq: {
    pageLead:
      "התשובות לשאלות שנוסעים באמת שואלים אותנו — על זכאות, סכומים, " +
      "התיישנות ומה קורה אחרי שמגישים.",
    title: "שאלות נפוצות",
    items: [
      {
        q: "הטיסה שלי בוטלה. האם בהכרח מגיע לי פיצוי?",
        a: "לא בהכרח. הזכאות תלויה בין היתר במועד ההודעה, בסיבת הביטול, במסלול ובנסיבות נוספות. הבדיקה של Skyclaim נועדה לבחון את המקרה הספציפי שלכם.",
      },
      {
        q: "כמה פיצוי אפשר לקבל?",
        a: "במקרים המתאימים הפיצוי עשוי להגיע לאלפי שקלים לכל נוסע, בהתאם למרחק הטיסה ולדין החל.",
      },
      {
        q: "גם ילדים זכאים לפיצוי?",
        a: "יש לבחון את סוג הכרטיס ואת נסיבות המקרה, אך במקרים רבים הזכאות נבחנת ביחס לכל נוסע בנפרד.",
      },
      {
        q: "קיבלתי טיסה חלופית. עדיין יכול להגיע לי כסף?",
        a: "ייתכן. עצם קבלת הטיסה החלופית לא בהכרח שוללת זכאות.",
      },
      {
        q: "חברת התעופה כבר דחתה אותי. עדיין אפשר לפנות?",
        a: "כן. תשובה של חברת התעופה אינה בהכרח סוף הבדיקה.",
      },
      {
        q: "אפשר לתבוע על טיסה שהייתה בעבר?",
        a: "במקרים רבים כן, בכפוף לתקופת ההתיישנות החלה על המקרה.",
      },
      {
        q: "מה לגבי הוצאות על מלון, אוכל ומוניות?",
        a: "ייתכן שניתן לדרוש גם החזר עבור הוצאות מסוימות. לכן חשוב לשמור קבלות.",
      },
      {
        q: "אילו מסמכים צריך?",
        a: "בשלב הראשון כמעט כלום. מתחילים מפרטי הטיסה, ובהמשך המערכת תגיד בדיוק אילו מסמכים דרושים.",
      },
    ] as const,
    more: "יש לכם שאלה שלא ענינו עליה?",
  },

  finalCta: {
    badge: "מייצגים נוסעים בלבד",
    title: "הטיסה השתבשה?",
    lead: "בואו נבדוק מה מגיע לכם.",
    body:
      "אותה מערכת, אותו תהליך — איתור הטיסה, בדיקת הזכאות, וטיפול מול חברת " +
      "התעופה. מתחילים בפחות מדקה.",
  },

  footer: {
    blurb: "פיצוי על טיסות שבוטלו או התעכבו. מייצגים נוסעים בלבד.",
    columns: [
      { title: "Skyclaim", links: ["בדיקת זכאות", "ביטולי טיסות", "עיכובים", "קונקשנים"] },
      { title: "אודות", links: ["עו״ד יצחק מימון", "שאלות נפוצות", "יצירת קשר"] },
      { title: "מידע משפטי", links: ["תנאי שימוש", "פרטיות", "נגישות"] },
    ] as const,
    rights: "© 2026 Skyclaim · עו״ד יצחק מימון",
    disclaimer:
      "המידע באתר אינו מהווה ייעוץ משפטי מחייב ואינו תחליף לבדיקה פרטנית.",
  },

  /** The claim wizard. */
  claim: {
    title: "התחלת תביעה",
    /**
     * REORDERED: contact details first, passengers second.
     *
     * The old order asked for every passenger's name and identity number
     * before asking who to reply to. That is backwards for two reasons. It
     * front-loads the slowest step onto somebody who has not yet committed
     * to anything, and it means an abandoned form leaves NO way to reach the
     * person -- the details we could have acted on are the ones we asked for
     * last.
     *
     * A phone number and an email arrive in thirty seconds. Everything after
     * them is worth asking for because somebody who has given them has
     * decided to go through with it.
     */
    steps: ["פרטים", "נוסעים", "הוצאות", "מסמכים", "סיכום"] as const,
    back: "חזרה",
    next: "המשך",

    /** Step one: who to reply to, and what happened. */
    contact: {
      title: "פרטים ליצירת קשר",
      body:
        "מספר נייד ואימייל, ואנחנו מתחילים לעבוד על התיק. " +
        "בלי שיחות מכירה — רק עדכונים על התביעה.",
      phone: "טלפון נייד",
      phoneHint: "לאימות ולעדכונים על התיק בלבד. בלי שיחות מכירה.",
      name: "שם מלא ליצירת קשר",
      email: "אימייל",
      whatHappened: "מה קרה בטיסה?",
      whatHappenedHint:
        "במילים שלכם. חברות תעופה לא חייבות לפצות כשהסיבה הייתה מחוץ " +
        "לשליטתן, אז זה קובע הרבה.",
      /**
       * What the airline has already given them.
       *
       * Asked because it changes the claim rather than merely describing it:
       * a voucher accepted at the desk is sometimes argued to settle the
       * matter, and care given -- a hotel, a meal -- is a separate
       * entitlement that does NOT reduce the compensation. Knowing which
       * happened decides how the letter is written.
       */
      alreadyGot: "קיבלתם כבר משהו מחברת התעופה?",
      alreadyGotHint: "לא חובה לענות, אבל זה עוזר לנו לבחור נכון את מסלול הדרישה.",
      alreadyGotOptions: [
        { value: "NOTHING", label: "לא קיבלנו כלום" },
        { value: "MONEY_OR_VOUCHER", label: "פיצוי כספי או שובר" },
        { value: "CARE", label: "רק סיוע: מלון, אוכל או טיסה חלופית" },
        { value: "BOTH", label: "גם פיצוי וגם סיוע" },
      ] as const,
      nextUp: "הצעד הבא: שמות הנוסעים, חצי דקה",
    },

    passengers: {
      title: "מי היה בהזמנה?",
      body:
        "הפיצוי משולם לכל נוסע, אז הוסיפו את כל מי שטס בהזמנה הזו — לא רק אתכם.",
      contactName: "השם המלא שלכם",
      contactEmail: "אימייל",
      contactEmailHint: "לכאן נשלח עדכונים על התביעה.",
      contactPhone: "טלפון (לא חובה)",
      fullName: "שם מלא כפי שמופיע בכרטיס",
      nationalId: "מספר תעודת זהות או דרכון",
      nationalIdHint: "חברות התעופה מבקשות את זה כדי לשייך אתכם להזמנה.",
      minor: "מתחת לגיל 18",
      add: "הוספת נוסע",
      remove: "הסרה",
      reference: "מספר הזמנה (PNR) — משותף לכל הנוסעים",
      referenceHint: "שישה תווים על הכרטיס, למשל ABC123.",
      anythingElse: "עוד משהו שכדאי שנדע? (לא חובה)",
      anythingElseHint:
        "תארו במילים שלכם פרטים נוספים על השיבוש, אם יש.",
    },

    booking: {
      title: "ההזמנה שלכם",
      body: "שני דברים ששום מאגר טיסות לא יודע — רק אתם.",
      reference: "מספר הזמנה",
      referenceHint: "שישה תווים על הכרטיס, למשל XJ4K2P.",
      airlineReason: "מה חברת התעופה אמרה שהייתה הסיבה?",
      airlineReasonHint:
        "במילים שלכם. חברות תעופה לא חייבות לפצות כשהסיבה הייתה מחוץ " +
        "לשליטתן, אז זה קובע הרבה.",
      notice: "אם הטיסה בוטלה — מתי חברת התעופה הודיעה לכם?",
      /**
       * Buckets, not a day count, and two of them are not quantities at all.
       *
       * "לא הודיעו לי" and "אני לא זוכר" are the answers that decide the most
       * claims, and a number cannot hold either: both collapse into a blank
       * that a claim handler cannot tell apart from an unanswered question.
       * The values match the backend's CancellationNotice.
       */
      noticeOptions: [
        { value: "", label: "הטיסה לא בוטלה" },
        { value: "NEVER_TOLD", label: "לא הודיעו לי בכלל" },
        { value: "ON_THE_DAY", label: "ביום הטיסה" },
        { value: "UNDER_A_WEEK", label: "פחות משבוע לפני" },
        { value: "ONE_TO_TWO_WEEKS", label: "שבוע עד שבועיים לפני" },
        { value: "OVER_TWO_WEEKS", label: "יותר משבועיים לפני" },
        { value: "CANNOT_REMEMBER", label: "אני לא זוכר" },
      ] as const,
    },

    costs: {
      title: "כמה זה עלה לכם?",
      body:
        "מלון, מוניות, אוכל ושיחות בגלל השיבוש מוחזרים בנוסף לפיצוי — לפי " +
        "העלות ומול קבלה. אפשר לדלג אם לא היו.",
      category: "על מה",
      amount: "סכום",
      currency: "מטבע",
      description: "תיאור (לא חובה)",
      add: "הוספת הוצאה",
      remove: "הסרה",
      none: "לא היו הוצאות מהכיס",
    },

    documents: {
      title: "העלו מה שיש לכם",
      body:
        "הכרטיס או אישור ההזמנה הם החשובים. קבלות מגבות את ההוצאות שרשמתם. " +
        "קובצי PDF או תמונות, עד 10MB כל אחד.",
      booking: "כרטיס או אישור הזמנה",
      receipt: "קבלות",
      boardingPass: "כרטיס עלייה למטוס (לא חובה)",
      drop: "בחרו קובץ",
      uploaded: "הועלה",
      later: "אפשר להוסיף עוד בהמשך — נשלח לכם קישור במייל.",
    },

    review: {
      title: "עברו על הפרטים",
      body: "אחרי השליחה אנחנו פונים לחברת התעופה בכתב.",
      passengers: "נוסעים",
      booking: "ההזמנה",
      costs: "הוצאות",
      documents: "מסמכים",
      submit: "שליחת התביעה",
      submitting: "שולחים…",
      consent:
        "בשליחה אתם מאשרים שהפרטים נכונים ומבקשים מאיתנו לטפל בתביעה " +
        "בשמכם.",
    },

    done: {
      title: "התביעה נשלחה",
      body:
        "אנחנו פונים לחברת התעופה ונעדכן אתכם במייל כשיהיו חדשות. שמרו את " +
        "מספר האסמכתא — כך תמצאו את התביעה בהמשך.",
      reference: "מספר האסמכתא שלכם",
    },

    errors: {
      needPassenger: "הוסיפו לפחות נוסע אחד כדי להמשיך.",
      needName: "הזינו את השם המלא של הנוסע.",
      needContactName: "צריך שם כדי לפתוח את התביעה.",
      needContactEmail: "צריך כתובת אימייל כדי לשלוח עדכונים.",
      badAmount: "הזינו סכום, למשל 42.50.",
    },
  },

  legal: {
    disclaimer: "זו הערכה אוטומטית ואינה ייעוץ משפטי.",
  },
} as const;

export type Strings = typeof strings;
