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
    headline: ["Flight delayed?", "You may be owed", "up to"] as const,
    maxAmount: "₪3,670",
    subhead:
      "Enter your flight number and the date it departed. We check what " +
      "actually happened to that flight against all three regulations and show " +
      "you the reasoning — not just a yes or no.",
    reassurance: "Free · No account · No card · Takes about ten seconds",
    footnote: "Every answer shows which law applied, which did not, and why.",
  },

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

  /** Headline and explanation per verdict. */
  verdict: {
    ELIGIBLE: {
      eyebrow: "Good news",
      lead: "You're owed compensation",
      underAmount: "under",
    },
    NOT_ELIGIBLE: {
      eyebrow: "Checked",
      /* Not "Sorry" and not "Unfortunately". This is a finding about an
         airline's obligation, not a rejection of the person reading it. */
      lead: "This flight doesn't qualify",
      explain:
        "Here's what each regulation said, so you can see exactly why.",
    },
    NEEDS_REVIEW: {
      eyebrow: "One more thing",
      /* Never a polite no. It has to be obvious this is unfinished. */
      lead: "We need to check this by hand",
      explain:
        "Something about this flight needs a person to look at it. That isn't " +
        "a no — it means we can't answer it automatically.",
    },
  },

  result: {
    notFoundLead: "We couldn't find that flight",
    ambiguousLead: "Which flight were you on?",
    ambiguousExplain:
      "More than one flight carried that number on that date. Pick yours and " +
      "we'll check it.",
    regulationsChecked: "What each regulation said",
    appliesYes: "Covers this flight",
    appliesNo: "Doesn't cover this flight",
    caveatTitle: "One thing we can't check",
    startClaim: "Start a claim",
    checkAnother: "Check another flight",
  },

  legal: {
    disclaimer: "This is an automated estimate, not legal advice.",
  },
} as const;

export type Strings = typeof strings;
