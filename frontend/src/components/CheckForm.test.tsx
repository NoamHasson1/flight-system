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

import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
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
  await user.type(screen.getByLabelText(/מספר טיסה/), number);
  const dateField = screen.getByLabelText(/תאריך הטיסה/);
  await user.clear(dateField);
  await user.type(dateField, date);
  await user.click(screen.getByRole("button", { name: /בדיקת זכאות/ }));
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
    await user.type(screen.getByLabelText(/מספר טיסה/), "B");

    expect(screen.queryByText(/זה לא נראה כמו מספר טיסה/)).toBeNull();
  });

  it("explains a malformed flight number once the field is left", async () => {
    const user = userEvent.setup();
    render(<CheckForm />);
    await user.type(screen.getByLabelText(/מספר טיסה/), "!!!");
    await user.tab();

    expect(
      await screen.findByText(/זה לא נראה כמו מספר טיסה/),
    ).toBeInTheDocument();
  });

  it("refuses to look up an invalid flight before calling the API", async () => {
    // The point of client-side validation: a typo costs nothing.
    const user = userEvent.setup();
    render(<CheckForm />);
    await user.click(screen.getByRole("button", { name: /בדיקת זכאות/ }));

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

    expect(await screen.findByText(/באיזו טיסה טסתם/)).toBeInTheDocument();
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

    expect(await screen.findByText(/אל תניחו שאין לכם תביעה/)).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });

  it("shows the server's own words on a rejected request", async () => {
    // The backend's validation messages are written for a person, name the
    // field that is wrong, and are in HEBREW -- which is what makes showing
    // them verbatim safe. A server speaking a different language from the
    // site is the reason this is worth asserting.
    checkEligibility.mockResolvedValue({
      ok: false,
      failure: { kind: "invalid", messages: ["התאריך הזה בעתיד."] },
    });
    await fillAndSubmit("BA165");

    expect(await screen.findByText(/התאריך הזה בעתיד/)).toBeInTheDocument();
  });
});

describe("while it is working", () => {
  it("says so, and cannot be submitted twice", async () => {
    // Double-clicking submit is the commonest thing a user does.
    let release: (value: unknown) => void = () => {};
    checkEligibility.mockReturnValue(new Promise((r) => (release = r)));

    const user = await fillAndSubmit("BA165");
    const button = await screen.findByRole("button", { name: /בודקים את הטיסה/ });
    expect(button).toBeDisabled();

    await user.click(button);
    expect(checkEligibility).toHaveBeenCalledTimes(1);

    release(decided());
  });
});

describe("a check that takes a while", () => {
  /**
   * The failure these cover, in full:
   *
   * A free host stops a service after a quarter of an hour of quiet. The next
   * visitor's check waits for it to boot -- measured at 21.9 seconds -- and
   * the browser used to give up at 20. Two seconds short. It then showed
   * "we couldn't reach the flight database", which is a sentence about the
   * flight database being down, when the answer was two seconds away.
   *
   * It failed for essentially every first visitor after a quiet spell.
   *
   * These drive the form with fireEvent rather than userEvent: userEvent
   * schedules its own timers between keystrokes, and under fake timers that
   * deadlocks against the clock the test is trying to control.
   */

  function submitWithFakeTimers() {
    render(<CheckForm />);
    fireEvent.change(screen.getByLabelText(/מספר טיסה/), {
      target: { value: "BA165" },
    });
    fireEvent.change(screen.getByLabelText(/תאריך הטיסה/), {
      target: { value: "2026-08-14" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: /בדיקת זכאות/ }),
    );
  }

  it("keeps waiting instead of calling a slow answer a failure", async () => {
    vi.useFakeTimers();
    try {
      let settle: (value: unknown) => void = () => {};
      checkEligibility.mockReturnValue(
        new Promise((resolve) => {
          settle = resolve;
        }),
      );
      submitWithFakeTimers();

      // Well past the old twenty-second ceiling.
      await vi.advanceTimersByTimeAsync(40_000);
      expect(screen.queryByText(/לא הצלחנו להגיע למאגר הטיסות/)).toBeNull();

      settle(decided());
      await vi.advanceTimersByTimeAsync(0);
      expect(push).toHaveBeenCalledWith("/check/abc-123");
    } finally {
      vi.useRealTimers();
    }
  });

  it("says what is happening rather than spinning in silence", async () => {
    // Somebody watching a silent spinner for thirty seconds closes the tab,
    // and a closed tab is a claim nobody ever hears about. The wait is real;
    // the silence is what loses the customer.
    vi.useFakeTimers();
    try {
      checkEligibility.mockReturnValue(new Promise(() => {}));
      submitWithFakeTimers();

      await vi.advanceTimersByTimeAsync(0);
      expect(screen.getByRole("button")).toHaveTextContent(
        /בודקים את הטיסה/,
      );

      // act(), because the state change originates in a timer rather than in
      // an event React already knows about.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(6_000);
      });
      expect(screen.getByRole("button")).toHaveTextContent(
        /יכול לקחת עד דקה/,
      );
    } finally {
      vi.useRealTimers();
    }
  });
});
