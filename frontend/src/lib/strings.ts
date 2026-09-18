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

  legal: {
    disclaimer: "This is an automated estimate, not legal advice.",
  },
} as const;

export type Strings = typeof strings;
