/**
 * Tests for the claim wizard.
 *
 * Five steps, one POST, and a draft that has to survive somebody closing the
 * tab to go and find a receipt. These test the things that lose a claim if
 * they break.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ClaimOut, EligibilityResponse } from "@/lib/api";

import { ClaimWizard } from "./ClaimWizard";

const createClaim = vi.fn();
const submitClaim = vi.fn();
const uploadDocument = vi.fn();

vi.mock("@/lib/api", () => ({
  createClaim: (...a: unknown[]) => createClaim(...a),
  submitClaim: (...a: unknown[]) => submitClaim(...a),
  uploadDocument: (...a: unknown[]) => uploadDocument(...a),
}));

/* Partial fixtures cast once, at the boundary, rather than `as never` at every
   use -- which is what stopped `{ ...CLAIM }` type-checking. */
const CHECK = {
  check_id: "check-1",
  status: "DECIDED",
  verdict: "ELIGIBLE",
  outcomes: [],
  options: [],
  provider: "fake",
} as unknown as EligibilityResponse;

const CLAIM = {
  id: "claim-1",
  reference: "FS-2026-K7M9QX",
  status: "DRAFT",
  passengers: [],
  expenses: [],
  documents: [],
  expense_totals: {},
} as unknown as ClaimOut;

beforeEach(() => {
  createClaim.mockReset();
  submitClaim.mockReset();
  uploadDocument.mockReset();
  window.localStorage.clear();
});

/**
 * Walk the first two steps: contact, then passengers.
 *
 * The order changed deliberately -- contact details come first now, because
 * they take thirty seconds and because a form abandoned after them still
 * leaves somebody we can write to. These tests drive the real flow rather
 * than a convenient shortcut, so the helper does the same clicking a person
 * would.
 */
async function fillContact(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText(/שם מלא ליצירת קשר/), "Noam Hasson");
  await user.type(screen.getByLabelText(/^אימייל$/), "noam@example.com");
  await user.click(screen.getByRole("button", { name: /המשך/ }));
}

/** Through contact and passengers, landing on costs. */
async function startClaim() {
  const user = userEvent.setup();
  render(<ClaimWizard check={CHECK} />);
  await fillContact(user);
  await user.type(screen.getByLabelText(/שם מלא כפי שמופיע בכרטיס/), "Noam Hasson");
  await user.click(screen.getByRole("button", { name: /המשך/ }));
  return user;
}

/**
 * Contact, passengers, costs -- landing on documents, which is the step that
 * creates the claim.
 *
 * Spelled out once. The old tests each walked forward by hand, which is why
 * every one of them broke the moment a step moved.
 */
async function toDocuments() {
  const user = await startClaim();
  await screen.findByText(/כמה זה עלה לכם/);
  await user.click(screen.getByRole("button", { name: /המשך/ }));
  await screen.findByText(/העלו מה שיש לכם/);
  return user;
}

/** Through contact only, landing on passengers. */
async function toPassengers() {
  const user = userEvent.setup();
  render(<ClaimWizard check={CHECK} />);
  await fillContact(user);
  return user;
}

describe("moving through the steps", () => {
  it("will not continue without a way to reach somebody", async () => {
    // A claim nobody can be reached about is a claim that never gets paid --
    // which is exactly why this is now the FIRST thing asked rather than
    // buried behind a page of identity numbers.
    const user = userEvent.setup();
    render(<ClaimWizard check={CHECK} />);
    await user.click(screen.getByRole("button", { name: /המשך/ }));

    expect(await screen.findByText(/צריך שם כדי לפתוח את התביעה/)).toBeInTheDocument();
    expect(screen.getByText(/פרטים ליצירת קשר/)).toBeInTheDocument();
  });

  it("will not leave the passengers step empty", async () => {
    // Compensation is per passenger; a claim with none has nobody to pay.
    const user = await toPassengers();
    await user.click(screen.getByRole("button", { name: /המשך/ }));

    expect(await screen.findByText(/הוסיפו לפחות נוסע אחד/)).toBeInTheDocument();
  });

  it("shows how far through you are", async () => {
    // "03 of 05" is the single thing that stops a long form being abandoned.
    await startClaim();
    expect(await screen.findByText(/3 מתוך 5/)).toBeInTheDocument();
  });

  it("lets you go back without losing what you typed", async () => {
    const user = await startClaim();
    await screen.findByText(/כמה זה עלה לכם/);

    // Back once lands on passengers, twice on contact. Both must still hold
    // what was typed -- a form that forgets a page when you check the
    // previous one is a form people restart from the top.
    await user.click(screen.getByRole("button", { name: /^חזרה$/ }));
    expect(screen.getByLabelText(/שם מלא כפי שמופיע בכרטיס/)).toHaveValue("Noam Hasson");

    await user.click(screen.getByRole("button", { name: /^חזרה$/ }));
    expect(screen.getByLabelText(/שם מלא ליצירת קשר/)).toHaveValue("Noam Hasson");
  });
});

describe("the questions the form no longer asks", () => {
  it("does not ask when the airline gave notice, or what happened", async () => {
    /**
     * Both were removed deliberately, and both still exist end to end.
     *
     * They are real questions that change how a letter is written. They
     * were just being asked of somebody who has this minute been told
     * they are owed money and wants to get on with it -- so they are now
     * asked later, by a person, once a claim exists. The columns, the
     * API fields and the admin screen are all untouched.
     *
     * This test exists so that "we took it out of the form" cannot
     * quietly become "we stopped collecting it at all".
     */
    render(<ClaimWizard check={CHECK} />);

    expect(screen.queryByLabelText(/מתי חברת התעופה הודיעה לכם/)).toBeNull();
    expect(screen.queryByLabelText(/מה קרה בטיסה/)).toBeNull();
    expect(screen.queryByText(/קיבלתם כבר משהו מחברת התעופה/)).toBeNull();
  });

  it("still creates a claim without them", async () => {
    /**
     * The fields are optional on the API and the form now sends null.
     * If that were ever rejected, the entire claim flow would be dead
     * and this is the cheapest place to find out.
     */
    createClaim.mockResolvedValue({ ok: true, data: CLAIM });
    const user = userEvent.setup();
    render(<ClaimWizard check={CHECK} />);

    await fillContact(user);
    await user.type(screen.getByLabelText(/שם מלא כפי שמופיע בכרטיס/), "Noam Hasson");
    await user.click(screen.getByRole("button", { name: /המשך/ }));
    await screen.findByText(/כמה זה עלה לכם/);
    await user.click(screen.getByRole("button", { name: /המשך/ }));

    await waitFor(() => expect(createClaim).toHaveBeenCalled());
    expect(createClaim.mock.calls[0][0]).toMatchObject({
      cancellation_notice: null,
      airline_reason: null,
    });
  });
});

describe("passengers", () => {
  it("adds and removes them, because compensation is per passenger", async () => {
    // A family of four is four awards. Getting this wrong quietly costs them
    // three quarters of the claim.
    const user = await toPassengers();
    await user.click(screen.getByRole("button", { name: /הוספת נוסע/ }));

    expect(screen.getAllByLabelText(/שם מלא כפי שמופיע בכרטיס/)).toHaveLength(2);

    await user.click(screen.getAllByRole("button", { name: /^הסרה$/ })[0]);
    expect(screen.getAllByLabelText(/שם מלא כפי שמופיע בכרטיס/)).toHaveLength(1);
  });
});

describe("the draft", () => {
  it("survives the page being reloaded", async () => {
    // People start a claim, go and find a receipt, and come back. Losing their
    // work at that moment is how a claim never gets filed.
    const user = userEvent.setup();
    const { unmount } = render(<ClaimWizard check={CHECK} />);
    await user.type(screen.getByLabelText(/שם מלא ליצירת קשר/), "Noam Hasson");
    await waitFor(() =>
      expect(window.localStorage.getItem("claim-draft:check-1")).toContain("Noam"),
    );

    unmount();
    render(<ClaimWizard check={CHECK} />);

    await waitFor(() =>
      expect(screen.getByLabelText(/שם מלא ליצירת קשר/)).toHaveValue("Noam Hasson"),
    );
  });

  it("keeps drafts for different checks apart", async () => {
    const user = userEvent.setup();
    render(<ClaimWizard check={CHECK} />);
    await user.type(screen.getByLabelText(/שם מלא ליצירת קשר/), "Noam Hasson");
    await waitFor(() =>
      expect(window.localStorage.getItem("claim-draft:check-1")).toBeTruthy(),
    );

    expect(window.localStorage.getItem("claim-draft:check-2")).toBeNull();
  });
});

describe("creating the claim", () => {
  it("posts everything in one request when documents are reached", async () => {
    // One POST rather than four: a claim assembled over several round trips can
    // fail on the third and leave a half-built record nobody will ever chase.
    createClaim.mockResolvedValue({ ok: true, data: CLAIM });

    await toDocuments();

    await waitFor(() => expect(createClaim).toHaveBeenCalledTimes(1));
    expect(createClaim).toHaveBeenCalledWith(
      expect.objectContaining({
        check_id: "check-1",
        contact_email: "noam@example.com",
        passengers: [expect.objectContaining({ full_name: "Noam Hasson" })],
      }),
    );
  });

  it("surfaces the server's refusal rather than a generic error", async () => {
    createClaim.mockResolvedValue({
      ok: false,
      failure: { kind: "refused", message: "This check already has a claim (FS-2026-AAAAAA)." },
    });

    const user = await startClaim();
    await screen.findByText(/כמה זה עלה לכם/);
    await user.click(screen.getByRole("button", { name: /המשך/ }));
    await user.click(await screen.findByRole("button", { name: /המשך/ }));

    expect(await screen.findByText(/FS-2026-AAAAAA/)).toBeInTheDocument();
  });

  it("does not create a second claim when you go back and forward again", async () => {
    // The claim exists after step three. Walking back and returning must not
    // make another one.
    createClaim.mockResolvedValue({ ok: true, data: CLAIM });

    const user = await toDocuments();

    await user.click(screen.getByRole("button", { name: /^חזרה$/ }));
    await user.click(await screen.findByRole("button", { name: /המשך/ }));

    expect(createClaim).toHaveBeenCalledTimes(1);
  });
});

describe("submitting", () => {
  it("shows the reference, because that is what they quote later", async () => {
    createClaim.mockResolvedValue({ ok: true, data: CLAIM });
    submitClaim.mockResolvedValue({
      ok: true,
      data: { ...CLAIM, status: "SUBMITTED" },
    });

    const user = await toDocuments();
    await user.click(screen.getByRole("button", { name: /המשך/ }));
    await user.click(await screen.findByRole("button", { name: /שליחת התביעה/ }));

    expect(await screen.findByText(/התביעה נשלחה/)).toBeInTheDocument();
    expect(screen.getByText("FS-2026-K7M9QX")).toBeInTheDocument();
  });

  it("clears the draft once submitted, so it cannot be resumed", async () => {
    createClaim.mockResolvedValue({ ok: true, data: CLAIM });
    submitClaim.mockResolvedValue({ ok: true, data: CLAIM });

    const user = await toDocuments();
    await user.click(screen.getByRole("button", { name: /המשך/ }));
    await user.click(await screen.findByRole("button", { name: /שליחת התביעה/ }));

    await waitFor(() =>
      expect(window.localStorage.getItem("claim-draft:check-1")).toBeNull(),
    );
  });
});

describe("the passenger count from the result screen", () => {
  /**
   * The counter on the verdict page is not decoration -- it changes the
   * amount shown there. Somebody who said "four of us" has already answered
   * this question, and asking again three screens later invites a different
   * answer that then disagrees with the figure which persuaded them to start.
   */

  it("opens with as many rows as the result screen was told", async () => {
    window.history.replaceState({}, "", "/claim/check-1?passengers=3");
    render(<ClaimWizard check={CHECK} />);
    await fillContact(userEvent.setup());

    expect(screen.getAllByLabelText(/שם מלא כפי שמופיע בכרטיס/)).toHaveLength(3);
  });

  it("refuses a count from the URL that is not a count", async () => {
    // It arrives in a query string, and a query string is typed by anyone.
    // Nine rows is a large family; nine hundred is someone poking at it.
    window.history.replaceState({}, "", "/claim/check-1?passengers=900");
    render(<ClaimWizard check={CHECK} />);
    await fillContact(userEvent.setup());

    expect(screen.getAllByLabelText(/שם מלא כפי שמופיע בכרטיס/)).toHaveLength(9);
  });

  it("falls back to one when nothing was passed", async () => {
    window.history.replaceState({}, "", "/claim/check-1");
    render(<ClaimWizard check={CHECK} />);
    await fillContact(userEvent.setup());

    expect(screen.getAllByLabelText(/שם מלא כפי שמופיע בכרטיס/)).toHaveLength(1);
  });
});

describe("catching a bad email where it is typed", () => {
  it("refuses to leave the contact step on a malformed address", async () => {
    /**
     * The exact failure a customer hit.
     *
     * The claim is only created at the END of the costs step, so an
     * address the server rejected surfaced two steps later -- as raw
     * English from Pydantic ("The part after the @-sign is not valid"),
     * on a page about hotel bills, about a field no longer on screen.
     * They had entered passengers and receipts before learning they had
     * mistyped their own email.
     */
    const user = userEvent.setup();
    render(<ClaimWizard check={CHECK} />);

    await user.type(screen.getByLabelText(/שם מלא ליצירת קשר/), "Noam Hasson");
    await user.type(screen.getByLabelText(/^אימייל$/), "noam@example");
    await user.click(screen.getByRole("button", { name: /המשך/ }));

    // Still on the contact step, with the field right there to correct.
    expect(screen.getByLabelText(/^אימייל$/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/שם מלא כפי שמופיע בכרטיס/)).toBeNull();
  });

  it("lets an ordinary address through", async () => {
    /**
     * The guard against over-correcting. Every regex that tries to
     * implement RFC 5322 rejects somebody's real address, and being told
     * "that is not an email" about one you have used for ten years is
     * worse than a server round trip. A plus-addressed, subdomained
     * address is perfectly normal and must pass.
     */
    const user = userEvent.setup();
    render(<ClaimWizard check={CHECK} />);

    await user.type(screen.getByLabelText(/שם מלא ליצירת קשר/), "Noam Hasson");
    await user.type(
      screen.getByLabelText(/^אימייל$/),
      "noam+claims@mail.example.co.il",
    );
    await user.click(screen.getByRole("button", { name: /המשך/ }));

    await screen.findByLabelText(/שם מלא כפי שמופיע בכרטיס/);
  });
});

describe("a receipt belongs to the expense it proves", () => {
  it("uploads it against that expense's id", async () => {
    /**
     * Receipts used to be collected in one pile on a later step, so
     * neither the customer nor we could tell afterwards which receipt
     * backed which charge -- which is exactly what an airline asks.
     *
     * The file cannot be sent when it is chosen: a document attaches to a
     * claim, and the claim does not exist until this step is submitted.
     * So it is held and sent immediately after, tagged with the id the
     * server gave that expense.
     */
    createClaim.mockResolvedValue({
      ok: true,
      data: { ...CLAIM, expenses: [{ id: "expense-1" }] },
    });
    uploadDocument.mockResolvedValue({
      ok: true,
      data: { document: { original_filename: "hotel.pdf" } },
    });

    const user = await startClaim();
    await user.click(screen.getByRole("button", { name: /הוספת הוצאה/ }));
    await user.type(screen.getByLabelText(/סכום/), "42.50");
    await user.upload(
      screen.getByLabelText(/בחרו קובץ/),
      new File(["x"], "hotel.pdf", { type: "application/pdf" }),
    );
    await user.click(screen.getByRole("button", { name: /המשך/ }));

    await waitFor(() => expect(uploadDocument).toHaveBeenCalled());
    const [claimId, file, kind, expenseId] = uploadDocument.mock.calls[0];
    expect(claimId).toBe("claim-1");
    expect((file as File).name).toBe("hotel.pdf");
    expect(kind).toBe("RECEIPT");
    expect(expenseId).toBe("expense-1");
  });

  it("does not lose the claim when a receipt will not upload", async () => {
    /**
     * The claim is the valuable thing and it is already saved by this
     * point. A photo that fails to upload can be added from the
     * documents step or the emailed link; losing the whole claim over it
     * would be a far worse trade.
     */
    createClaim.mockResolvedValue({
      ok: true,
      data: { ...CLAIM, expenses: [{ id: "expense-1" }] },
    });
    uploadDocument.mockResolvedValue({ ok: false, failure: { kind: "unreachable" } });

    const user = await startClaim();
    await user.click(screen.getByRole("button", { name: /הוספת הוצאה/ }));
    await user.type(screen.getByLabelText(/סכום/), "42.50");
    await user.upload(
      screen.getByLabelText(/בחרו קובץ/),
      new File(["x"], "hotel.pdf", { type: "application/pdf" }),
    );
    await user.click(screen.getByRole("button", { name: /המשך/ }));

    // Moved on to documents regardless.
    await screen.findByText(/העלו מה שיש לכם/);
  });

  it("no longer asks for receipts on the documents step", async () => {
    /**
     * They are collected with the expenses now. Leaving the old field
     * there would invite somebody to upload the same receipt twice, in
     * the one place where it loses its link to a charge.
     */
    createClaim.mockResolvedValue({ ok: true, data: CLAIM });
    const user = await startClaim();
    await user.click(screen.getByRole("button", { name: /המשך/ }));

    await screen.findByText(/העלו מה שיש לכם/);
    expect(screen.queryByText(/^קבלות$/)).toBeNull();
    expect(screen.getByText(/כרטיס או אישור הזמנה/)).toBeInTheDocument();
  });
});
