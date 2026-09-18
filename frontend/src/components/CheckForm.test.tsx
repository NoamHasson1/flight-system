/**
 * Tests for the check form.
 *
 * What is tested here is what a customer can do wrong and what the form owes
 * them in return -- not that Tailwind applied a class. Every case below is a
 * real behaviour with a cost attached if it breaks.
 *
 * The API module is mocked at the boundary rather than the network: these are
 * tests of the form's behaviour, and the client itself is exercised against a
 * real server by the end-to-end run.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CheckForm } from "./CheckForm";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const checkEligibility = vi.fn();
vi.mock("@/lib/api", () => ({
  checkEligibility: (...args: unknown[]) => checkEligibility(...args),
}));

function decided(overrides: Record<string, unknown> = {}) {
  return {
    ok: true,
    data: { check_id: "abc-123", status: "DECIDED", options: [], ...overrides },
  };
}

beforeEach(() => {
  push.mockReset();
  checkEligibility.mockReset();
});

async function fillAndSubmit(number: string, date = "2026-08-14") {
  const user = userEvent.setup();
  render(<CheckForm />);
  await user.type(screen.getByLabelText(/flight number/i), number);
  const dateField = screen.getByLabelText(/date it departed/i);
  await user.clear(dateField);
  await user.type(dateField, date);
  await user.click(screen.getByRole("button", { name: /see what you're owed/i }));
  return user;
}

describe("what the customer types", () => {
  it("normalises the flight number before spending a lookup", async () => {
    // "ba 165", "BA-165" and "ba165" are the same flight. None of them should
    // cost an API call to discover that.
    checkEligibility.mockResolvedValue(decided());
    await fillAndSubmit("ba 165");

    await waitFor(() => expect(checkEligibility).toHaveBeenCalled());
    expect(checkEligibility).toHaveBeenCalledWith(
      expect.objectContaining({ flight_number: "BA165" }),
    );
  });

  it("does not complain while they are still typing", async () => {
    // Telling somebody their flight number is wrong on the second character
    // is correct and useless.
    const user = userEvent.setup();
    render(<CheckForm />);
    await user.type(screen.getByLabelText(/flight number/i), "B");

    expect(screen.queryByText(/doesn't look like a flight number/i)).toBeNull();
  });

  it("explains a malformed flight number once the field is left", async () => {
    const user = userEvent.setup();
    render(<CheckForm />);
    await user.type(screen.getByLabelText(/flight number/i), "!!!");
    await user.tab();

    expect(
      await screen.findByText(/doesn't look like a flight number/i),
    ).toBeInTheDocument();
  });

  it("refuses to look up an invalid flight before calling the API", async () => {
    // The point of client-side validation: a typo costs nothing.
    const user = userEvent.setup();
    render(<CheckForm />);
    await user.click(screen.getByRole("button", { name: /see what you're owed/i }));

    expect(checkEligibility).not.toHaveBeenCalled();
  });
});

describe("what comes back", () => {
  it("sends a decided check to its own URL", async () => {
    // The result gets a URL so it survives a refresh and can be shared.
    checkEligibility.mockResolvedValue(decided({ check_id: "xyz-789" }));
    await fillAndSubmit("BA165");

    await waitFor(() => expect(push).toHaveBeenCalledWith("/check/xyz-789"));
  });

  it("asks which flight when more than one matches", async () => {
    // FR1234 flew Dublin to Stansted twice that day. Guessing would tell half
    // those passengers a confident answer about a journey they did not take.
    checkEligibility.mockResolvedValue(
      decided({
        status: "AMBIGUOUS",
        message: "2 flights carried that number.",
        options: [
          { key: "a", route: "DUB → STN", label: "DUB → STN, departing 06:00 UTC", scheduled_departure: null },
          { key: "b", route: "DUB → STN", label: "DUB → STN, departing 16:00 UTC", scheduled_departure: null },
        ],
      }),
    );
    await fillAndSubmit("FR1234");

    expect(await screen.findByText(/which flight were you on/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /departing 06:00 UTC/i })).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });

  it("re-checks with the chosen flight", async () => {
    checkEligibility
      .mockResolvedValueOnce(
        decided({
          status: "AMBIGUOUS",
          options: [{ key: "evening", route: "DUB → STN", label: "DUB → STN, departing 16:00 UTC", scheduled_departure: null }],
        }),
      )
      .mockResolvedValueOnce(decided({ check_id: "chosen-1" }));

    const user = await fillAndSubmit("FR1234");
    await user.click(await screen.findByRole("button", { name: /departing 16:00 UTC/i }));

    await waitFor(() =>
      expect(checkEligibility).toHaveBeenLastCalledWith(
        expect.objectContaining({ option_key: "evening" }),
      ),
    );
  });

  it("never turns a failed lookup into a verdict", async () => {
    // The most expensive bug this product could have. Somebody who reads an
    // error and closes the tab has lost a claim nobody will ever know about,
    // so the message has to say the failure is ours.
    checkEligibility.mockResolvedValue({
      ok: false,
      failure: { kind: "unreachable" },
    });
    await fillAndSubmit("BA165");

    expect(await screen.findByText(/don't assume you have no claim/i)).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });

  it("shows the server's own words on a rejected request", async () => {
    // The backend's validation messages are written for humans -- "That date
    // is in the future" -- so they are worth surfacing rather than replacing.
    checkEligibility.mockResolvedValue({
      ok: false,
      failure: { kind: "invalid", messages: ["That date is in the future."] },
    });
    await fillAndSubmit("BA165");

    expect(await screen.findByText(/that date is in the future/i)).toBeInTheDocument();
  });
});

describe("while it is working", () => {
  it("says so, and cannot be submitted twice", async () => {
    // Double-clicking submit is the commonest thing a user does.
    let release: (value: unknown) => void = () => {};
    checkEligibility.mockReturnValue(new Promise((r) => (release = r)));

    const user = await fillAndSubmit("BA165");
    const button = await screen.findByRole("button", { name: /checking your flight/i });
    expect(button).toBeDisabled();

    await user.click(button);
    expect(checkEligibility).toHaveBeenCalledTimes(1);

    release(decided());
  });
});
