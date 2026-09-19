/**
 * Tests for the claim wizard.
 *
 * Five steps, one POST, and a draft that has to survive somebody closing the
 * tab to go and find a receipt. These test the things that lose a claim if
 * they break.
 */

import { render, screen, waitFor, within } from "@testing-library/react";
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

/** Fill step one and move to step two. */
async function startClaim() {
  const user = userEvent.setup();
  render(<ClaimWizard check={CHECK} />);
  await user.type(screen.getByLabelText(/your full name/i), "Noam Hasson");
  await user.type(screen.getByLabelText(/^email$/i), "noam@example.com");
  await user.type(screen.getByLabelText(/full name on the ticket/i), "Noam Hasson");
  await user.click(screen.getByRole("button", { name: /continue/i }));
  return user;
}

describe("moving through the steps", () => {
  it("will not continue without a contact and a passenger", async () => {
    // A claim nobody can be reached about is a claim that never gets paid.
    const user = userEvent.setup();
    render(<ClaimWizard check={CHECK} />);
    await user.click(screen.getByRole("button", { name: /continue/i }));

    expect(await screen.findByText(/name to put on the claim/i)).toBeInTheDocument();
    expect(screen.getByText(/who was on the booking/i)).toBeInTheDocument();
  });

  it("shows how far through you are", async () => {
    // "03 of 05" is the single thing that stops a long form being abandoned.
    await startClaim();
    expect(await screen.findByText(/02 of 05/i)).toBeInTheDocument();
  });

  it("lets you go back without losing what you typed", async () => {
    const user = await startClaim();
    await screen.findByText(/your booking/i);
    await user.click(screen.getByRole("button", { name: /^back$/i }));

    expect(screen.getByLabelText(/your full name/i)).toHaveValue("Noam Hasson");
  });
});

describe("when the airline told them", () => {
  it("offers the two answers a number cannot hold", async () => {
    // The whole reason this stopped being a day count.
    //
    // "They never told me" is the strongest possible answer -- no notice at
    // all -- and "I can't remember" is the honest one. Neither is a quantity,
    // so an integer field turned both into a blank that a claim handler could
    // not tell apart from a question nobody asked.
    const user = await startClaim();
    await screen.findByText(/your booking/i);

    const select = screen.getByLabelText(/when did the airline tell you/i);
    expect(
      within(select).getByRole("option", { name: /never told me/i }),
    ).toBeInTheDocument();
    expect(
      within(select).getByRole("option", { name: /can't remember/i }),
    ).toBeInTheDocument();

    await user.selectOptions(select, "NEVER_TOLD");
    expect(select).toHaveValue("NEVER_TOLD");
  });

  it("sends the answer as the backend's own vocabulary", async () => {
    // The values are the CancellationNotice enum, not labels and not days. A
    // mismatch here is rejected by the API, so it must be pinned somewhere.
    createClaim.mockResolvedValue({ ok: true, data: CLAIM });
    const user = await startClaim();
    await screen.findByText(/your booking/i);

    await user.selectOptions(
      screen.getByLabelText(/when did the airline tell you/i),
      "ONE_TO_TWO_WEEKS",
    );
    await user.click(screen.getByRole("button", { name: /continue/i }));
    await screen.findByText(/what did it cost you/i);
    await user.click(screen.getByRole("button", { name: /continue/i }));

    await waitFor(() => expect(createClaim).toHaveBeenCalled());
    expect(createClaim.mock.calls[0][0]).toMatchObject({
      cancellation_notice: "ONE_TO_TWO_WEEKS",
    });
  });
});

describe("passengers", () => {
  it("adds and removes them, because compensation is per passenger", async () => {
    // A family of four is four awards. Getting this wrong quietly costs them
    // three quarters of the claim.
    const user = userEvent.setup();
    render(<ClaimWizard check={CHECK} />);
    await user.click(screen.getByRole("button", { name: /add another passenger/i }));

    expect(screen.getAllByLabelText(/full name on the ticket/i)).toHaveLength(2);

    await user.click(screen.getAllByRole("button", { name: /^remove$/i })[0]);
    expect(screen.getAllByLabelText(/full name on the ticket/i)).toHaveLength(1);
  });
});

describe("the draft", () => {
  it("survives the page being reloaded", async () => {
    // People start a claim, go and find a receipt, and come back. Losing their
    // work at that moment is how a claim never gets filed.
    const user = userEvent.setup();
    const { unmount } = render(<ClaimWizard check={CHECK} />);
    await user.type(screen.getByLabelText(/your full name/i), "Noam Hasson");
    await waitFor(() =>
      expect(window.localStorage.getItem("claim-draft:check-1")).toContain("Noam"),
    );

    unmount();
    render(<ClaimWizard check={CHECK} />);

    await waitFor(() =>
      expect(screen.getByLabelText(/your full name/i)).toHaveValue("Noam Hasson"),
    );
  });

  it("keeps drafts for different checks apart", async () => {
    const user = userEvent.setup();
    render(<ClaimWizard check={CHECK} />);
    await user.type(screen.getByLabelText(/your full name/i), "Noam Hasson");
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

    const user = await startClaim();
    await screen.findByText(/your booking/i);
    await user.click(screen.getByRole("button", { name: /continue/i }));
    await screen.findByText(/what did it cost you/i);
    await user.click(screen.getByRole("button", { name: /continue/i }));

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
    await screen.findByText(/your booking/i);
    await user.click(screen.getByRole("button", { name: /continue/i }));
    await user.click(await screen.findByRole("button", { name: /continue/i }));

    expect(await screen.findByText(/FS-2026-AAAAAA/)).toBeInTheDocument();
  });

  it("does not create a second claim when you go back and forward again", async () => {
    // The claim exists after step three. Walking back and returning must not
    // make another one.
    createClaim.mockResolvedValue({ ok: true, data: CLAIM });

    const user = await startClaim();
    await screen.findByText(/your booking/i);
    await user.click(screen.getByRole("button", { name: /continue/i }));
    await user.click(await screen.findByRole("button", { name: /continue/i }));
    await screen.findByText(/upload what you have/i);

    await user.click(screen.getByRole("button", { name: /^back$/i }));
    await user.click(await screen.findByRole("button", { name: /continue/i }));

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

    const user = await startClaim();
    await screen.findByText(/your booking/i);
    await user.click(screen.getByRole("button", { name: /continue/i }));
    await user.click(await screen.findByRole("button", { name: /continue/i }));
    await screen.findByText(/upload what you have/i);
    await user.click(screen.getByRole("button", { name: /continue/i }));
    await user.click(await screen.findByRole("button", { name: /submit my claim/i }));

    expect(await screen.findByText(/your claim is in/i)).toBeInTheDocument();
    expect(screen.getByText("FS-2026-K7M9QX")).toBeInTheDocument();
  });

  it("clears the draft once submitted, so it cannot be resumed", async () => {
    createClaim.mockResolvedValue({ ok: true, data: CLAIM });
    submitClaim.mockResolvedValue({ ok: true, data: CLAIM });

    const user = await startClaim();
    await screen.findByText(/your booking/i);
    await user.click(screen.getByRole("button", { name: /continue/i }));
    await user.click(await screen.findByRole("button", { name: /continue/i }));
    await screen.findByText(/upload what you have/i);
    await user.click(screen.getByRole("button", { name: /continue/i }));
    await user.click(await screen.findByRole("button", { name: /submit my claim/i }));

    await waitFor(() =>
      expect(window.localStorage.getItem("claim-draft:check-1")).toBeNull(),
    );
  });
});
