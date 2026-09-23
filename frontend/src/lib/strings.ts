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
    how: "איך זה עובד",
    eligibility: "זכאות לפיצוי",
    board: "לוח שיבושים",
    faq: "שאלות נפוצות",
    about: "אודות",
    cta: "בדיקת זכאות",
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
    startClaim: "התחילו תביעה",
    askHuman: "בקשו בדיקה ידנית",
    checkAnother: "בדקו טיסה נוספת",
  },

  /** The live disruptions board, built from our own archive. */
  board: {
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

  /** EMPTY until real, attributable reviews exist. See `lawyer.credentials`. */
  testimonials: {
    title: "נוסעים שכבר עברו את זה.",
    items: [] as readonly { quote: string; name: string; when: string }[],
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

  faq: {
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
    steps: ["נוסעים", "ההזמנה", "הוצאות", "מסמכים", "סיכום"] as const,
    back: "חזרה",
    next: "המשך",

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
