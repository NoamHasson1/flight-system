/**
 * Every word the customer reads, in one file.
 *
 * Two reasons it lives here rather than inline in components.
 *
 * First, Hebrew. The Israeli market is half the point of this product, and
 * retrofitting translation into forty components is a rewrite while adding a
 * second object here is an afternoon. The English is written to be
 * translatable: no sentences assembled from fragments, no "you have {n}
 * claim(s)" that only works in languages with one plural rule.
 *
 * Second, tone. This product tells people about money and the law at a moment
 * when something has already gone wrong for them. Keeping the copy together is
 * the only way to notice that one screen is reassuring and the next sounds like
 * a bank. The rules: plain words over legal ones, never blame the reader, and
 * never claim more certainty than we have.
 */

export const strings = {
  brand: {
    name: "Skyclaim",
    tagline: "EC261 · UK261 · Israeli Aviation Services Law",
  },

  hero: {
    headlineA: "Flight delayed?",
    headlineB: "You may be owed money.",
    subhead:
      "Enter your flight number and the date it departed. We check what " +
      "actually happened to that flight and tell you in seconds whether you " +
      "can claim — and how much.",
    cardTitle: "Check what you're owed",
    reassurance: "Free · No account · No card",
  },

  /** The four reassurances under the hero, straight from the reference. */
  stats: [
    { value: "Up to €600", label: "per passenger for delays, cancellations and denied boarding" },
    { value: "Three laws", label: "EU, UK and Israeli rules checked on every flight" },
    { value: "No risk", label: "the check is free and you are never charged to find out" },
    { value: "Seconds", label: "an answer before you have finished your coffee" },
  ] as const,

  steps: [
    { n: "1", title: "Enter your flight", body: "The flight number and the date it departed. Nothing else." },
    { n: "2", title: "We check it", body: "We look up what actually happened to that flight and apply the rules." },
    { n: "3", title: "You claim", body: "If you qualify, add your passengers and receipts and we take it from there." },
  ] as const,

  form: {
    flightNumberLabel: "Flight number",
    flightNumberPlaceholder: "BA165",
    flightNumberHint: "The airline code and number, like BA165 or LY324.",
    dateLabel: "Date it departed",
    dateHint: "The day the flight took off, not the day you booked.",
    submit: "See what you're owed",
    submitting: "Checking your flight…",
  },

  /**
   * Errors the customer can act on.
   *
   * None of these say "error" and none of them blame the reader. A person
   * whose flight was cancelled and who is now being told they typed something
   * wrong is having a worse day than whoever wrote the message.
   */
  errors: {
    flightNumberRequired: "Enter the flight number from your booking.",
    flightNumberFormat:
      "That doesn't look like a flight number. It's usually two letters and " +
      "some digits, like BA165.",
    dateRequired: "Enter the date the flight departed.",
    emailFormat: "That doesn't look like an email address.",
    dateFuture:
      "That date is in the future. Enter the date the flight departed — we " +
      "can only check flights that have already taken off.",
    dateTooOld:
      "That flight is more than six years ago, which is beyond the time limit " +
      "for claiming in every country we cover.",
    /**
     * The most important string in this file.
     *
     * Someone who reads "something went wrong" and closes the tab has lost a
     * claim nobody will ever know about. It has to say, explicitly, that this
     * is not an answer about their flight.
     */
    unreachable:
      "We couldn't reach the flight database just now. This is a problem on " +
      "our side and says nothing about your flight — please try again in a " +
      "moment, and don't assume you have no claim.",
  },

  /**
   * The verdict, in plain words.
   *
   * Deliberately NO regulation names, thresholds or clause-by-clause
   * reasoning: the customer asked a simple question and gets a simple answer.
   * All of that reasoning is still computed and still STORED against the check
   * -- it is what support and the claim handler work from -- it just is not
   * what this screen is for.
   */
  verdict: {
    ELIGIBLE: {
      eyebrow: "Good news",
      lead: "You can claim compensation",
      amountLabel: "per passenger on the booking",
    },
    NOT_ELIGIBLE: {
      eyebrow: "Checked",
      /* Not "Sorry" and not "Unfortunately". This is a finding about an
         airline's obligation, not a rejection of the person reading it. */
      lead: "This flight doesn't qualify",
      body:
        "Nothing here is down to anything you did. Compensation depends on how " +
        "late the flight actually was and on where it flew, and this one falls " +
        "outside those limits.",
      doubt:
        "If you landed later than we show, or the airline told you something " +
        "different, ask us to check it by hand.",
    },
    NEEDS_REVIEW: {
      eyebrow: "One more thing",
      /* Never a polite no. It has to be obvious this is unfinished. */
      lead: "We need to check this by hand",
      body:
        "Something about this flight can't be answered automatically. That is " +
        "not a no — leave us your email and a person will come back to you.",
    },
    /**
     * The amount is real and the law is settled. One fact is missing, and the
     * person reading this is the only one who has it.
     *
     * Showing the figure is the point. "We'll look into it" and "you are owed
     * 1,530 shekels, subject to one question" describe the same state of
     * knowledge, and only one of them gets answered.
     */
    LIKELY_ELIGIBLE: {
      eyebrow: "Almost certainly",
      lead: "You look owed",
      amountLabel: "per passenger, subject to one question",
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
      title: "When did the airline tell you?",
      /* The law, in one sentence, so the question does not read as an
         obstacle invented by us. */
      explain:
        "Two weeks' notice or more lets the airline off. Less than that, and " +
        "this is payable.",
      options: [
        { value: "NEVER_TOLD", label: "They never told me" },
        { value: "ON_THE_DAY", label: "On the day of the flight" },
        { value: "UNDER_A_WEEK", label: "Less than a week before" },
        { value: "ONE_TO_TWO_WEEKS", label: "One to two weeks before" },
        { value: "OVER_TWO_WEEKS", label: "More than two weeks before" },
        { value: "CANNOT_REMEMBER", label: "I can't remember" },
      ],
    },
    actual_arrival: {
      title: "When did you actually land?",
      explain:
        "Your flight left late enough to qualify whatever happened next. If " +
        "the airline still got you there close to schedule, the amount halves.",
      options: [] as const,
    },
  },

  result: {
    notFoundLead: "We couldn't find that flight",
    ambiguousLead: "Which flight were you on?",
    ambiguousExplain:
      "More than one flight carried that number on that date. Pick yours and " +
      "we'll check it.",
    yourFlight: "Your flight",
    whatNext: "What happens next",
    nextSteps: [
      "Add the passengers on your booking and upload your ticket.",
      "We put the claim to the airline in writing, citing the rule that applies.",
      "You get paid. We only take a fee if the claim succeeds.",
    ] as const,
    caveat:
      "Airlines don't have to pay when the cause was outside their control — " +
      "severe weather, for instance. We'll ask what you were told.",
    startClaim: "Start my claim",
    askHuman: "Ask us to check by hand",
    checkAnother: "Check another flight",
  },

  /** The claim wizard. */
  claim: {
    title: "Start your claim",
    steps: ["Passengers", "Booking", "Costs", "Documents", "Review"] as const,
    back: "Back",
    next: "Continue",

    passengers: {
      title: "Who was on the booking?",
      body:
        "Compensation is paid per passenger, so add everyone who travelled on " +
        "this booking — not just you.",
      contactName: "Your full name",
      contactEmail: "Email",
      contactEmailHint: "This is where we send updates about the claim.",
      contactPhone: "Phone (optional)",
      fullName: "Full name on the ticket",
      nationalId: "ID or passport number",
      nationalIdHint: "Airlines ask for this to match you to the booking.",
      minor: "Under 18",
      add: "Add another passenger",
      remove: "Remove",
    },

    booking: {
      title: "Your booking",
      body: "Two things no flight database can tell us — only you can.",
      reference: "Booking reference",
      referenceHint: "Six characters on your ticket, like XJ4K2P.",
      airlineReason: "What did the airline say was the reason?",
      airlineReasonHint:
        "In your own words. Airlines don't have to pay when the cause was " +
        "outside their control, so this decides a lot.",
      notice: "If the flight was cancelled, when did the airline tell you?",
      /**
       * Buckets, not a day count, and two of them are not quantities at all.
       *
       * "They never told me" and "I can't remember" are the answers that decide
       * the most claims, and a number cannot hold either: both collapse into a
       * blank that a claim handler cannot tell apart from an unanswered
       * question. The values match the backend's CancellationNotice.
       */
      noticeOptions: [
        { value: "", label: "It wasn't cancelled" },
        { value: "NEVER_TOLD", label: "They never told me" },
        { value: "ON_THE_DAY", label: "On the day of the flight" },
        { value: "UNDER_A_WEEK", label: "Less than a week before" },
        { value: "ONE_TO_TWO_WEEKS", label: "One to two weeks before" },
        { value: "OVER_TWO_WEEKS", label: "More than two weeks before" },
        { value: "CANNOT_REMEMBER", label: "I can't remember" },
      ] as const,
    },

    costs: {
      title: "What did it cost you?",
      body:
        "Hotels, taxis, meals and calls caused by the disruption are reimbursed " +
        "on top of the compensation — at cost, against a receipt. Skip this if " +
        "there weren't any.",
      category: "What was it",
      amount: "Amount",
      currency: "Currency",
      description: "Description (optional)",
      add: "Add a cost",
      remove: "Remove",
      none: "No out-of-pocket costs",
    },

    documents: {
      title: "Upload what you have",
      body:
        "Your ticket or booking confirmation is the important one. Receipts " +
        "back up the costs you listed. PDFs or photos, up to 10 MB each.",
      booking: "Ticket or booking confirmation",
      receipt: "Receipts",
      boardingPass: "Boarding pass (optional)",
      drop: "Choose a file",
      uploaded: "Uploaded",
      later: "You can add more later — we'll email you a link.",
    },

    review: {
      title: "Check it over",
      body: "Once you submit, we put the claim to the airline in writing.",
      passengers: "Passengers",
      booking: "Booking",
      costs: "Costs",
      documents: "Documents",
      submit: "Submit my claim",
      submitting: "Submitting…",
      consent:
        "By submitting you confirm the details are accurate and ask us to " +
        "pursue this claim on your behalf.",
    },

    done: {
      title: "Your claim is in",
      body:
        "We'll put it to the airline and email you when there's news. Keep this " +
        "reference — it's how you or we find the claim later.",
      reference: "Your claim reference",
    },

    errors: {
      needPassenger: "Add at least one passenger before continuing.",
      needName: "Enter this passenger's full name.",
      needContactName: "We need a name to put on the claim.",
      needContactEmail: "We need an email address to send updates to.",
      badAmount: "Enter an amount, like 42.50.",
    },
  },

  legal: {
    disclaimer: "This is an automated estimate, not legal advice.",
  },
} as const;

export type Strings = typeof strings;
