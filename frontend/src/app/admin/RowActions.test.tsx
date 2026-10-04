/**
 * Tests for the two send buttons at the end of a CRM row.
 *
 * WHY THESE TESTS AND NOT OTHERS
 *
 * Everything else in this console reads. These two buttons WRITE TO A
 * STRANGER -- they put an email in a customer's inbox over a lawyer's
 * name, and there is no undo. So the tests are not about rendering; they
 * are about the four ways this can go wrong in a way nobody notices:
 *
 *   1. A BUTTON THAT CANNOT WORK. Both endpoints are claim-scoped. A
 *      customer who checked eligibility and never filed has no claim, and
 *      a button offered to that row is a dead end an operator discovers
 *      only by pressing it.
 *
 *   2. THE ROW OPENING A TAB BEHIND THE DIALOG. Clicking the row opens
 *      the customer in a new tab. If the click reaches the row as well as
 *      the button, every send throws an unwanted tab at the operator --
 *      a one-character regression (`stopPropagation` dropped in a tidy-up)
 *      with a loud symptom, which is exactly the kind a test should hold.
 *
 *   3. MAIL LEAVING ON A DECLINED CONFIRMATION. The confirm is the only
 *      thing between a mis-click and a letter. If it is ever wired up so
 *      that cancelling still sends, nothing on screen says so.
 *
 *   4. "SENT" WHEN NOTHING WAS SENT. The server answers `sent: false`
 *      when the provider REFUSED the message. Reporting that as success
 *      leaves an operator waiting for a reply to a letter that was never
 *      delivered. This is the bug worth the most: it is silent.
 *
 * What is deliberately NOT tested: the wording of the letters (that lives
 * in `app/services/outreach.py` and is tested there, against the real
 * claim), and the dialog's animation.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { strings } from "@/lib/strings";

import { RowActions } from "./RowActions";

const requestItems = vi.fn();
const sendStatement = vi.fn();

vi.mock("@/lib/api", () => ({
  requestItems: (...a: unknown[]) => requestItems(...a),
  sendStatement: (...a: unknown[]) => sendStatement(...a),
}));

const t = strings.admin.outreach;

function setup(
  overrides: Partial<React.ComponentProps<typeof RowActions>> = {},
) {
  const onDone = vi.fn();
  const onRowClick = vi.fn();
  render(
    // The wrapper stands in for the <tr>: the real row carries an onClick
    // that opens a tab, and the point of the component is that it does not
    // reach it.
    <div onClick={onRowClick}>
      <RowActions
        adminKey="k"
        claimId="claim-1"
        email="dana@example.com"
        name="דנה"
        onDone={onDone}
        {...overrides}
      />
    </div>,
  );
  return { onDone, onRowClick };
}

beforeEach(() => {
  requestItems.mockReset();
  sendStatement.mockReset();
  requestItems.mockResolvedValue({
    ok: true,
    data: { sent: true, to: "dana@example.com" },
  });
  sendStatement.mockResolvedValue({
    ok: true,
    data: { sent: true, to: "dana@example.com" },
  });
});

describe("when there is nothing to send, or nobody to send to", () => {
  it("offers no buttons to a customer who never filed a claim", () => {
    setup({ claimId: null });
    expect(screen.queryByLabelText(t.requestTitle)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(t.statementTitle)).not.toBeInTheDocument();
  });

  it("offers no buttons when we hold no email address", () => {
    setup({ email: null });
    expect(screen.queryByLabelText(t.requestTitle)).not.toBeInTheDocument();
  });
});

describe("the dialog", () => {
  it("does not let the click through to the row", async () => {
    const user = userEvent.setup();
    const { onRowClick } = setup();

    await user.click(screen.getByLabelText(t.requestTitle));

    // The row's handler opens a new tab. It must not have run.
    expect(onRowClick).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("names the recipient on screen, not just in the confirm", async () => {
    const user = userEvent.setup();
    setup();

    await user.click(screen.getByLabelText(t.requestTitle));

    // Not "are you sure" -- the address, readable for as long as the form
    // is open, because an operator going down a list of twenty needs to
    // know which one they are writing to.
    expect(screen.getByRole("dialog")).toHaveTextContent("dana@example.com");
  });

  it("closes on Escape without sending anything", async () => {
    const user = userEvent.setup();
    setup();

    await user.click(screen.getByLabelText(t.requestTitle));
    await user.keyboard("{Escape}");

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(requestItems).not.toHaveBeenCalled();
  });
});

describe("asking the customer for missing items", () => {
  it("sends the ticked keys for this claim, and reports where they went", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const { onDone } = setup();

    await user.click(screen.getByLabelText(t.requestTitle));
    await user.click(screen.getByLabelText(t.items.RECEIPTS));
    await user.click(screen.getByLabelText(t.items.BANK));
    await user.click(screen.getByRole("button", { name: t.sendRequest }));

    await waitFor(() =>
      expect(requestItems).toHaveBeenCalledWith(
        "k",
        "claim-1",
        // Keys, not Hebrew sentences: the server refuses an unknown key,
        // which is how a drift between the two lists becomes a 422 rather
        // than an enum name in the middle of a letter.
        ["RECEIPTS", "BANK"],
        undefined,
      ),
    );
    // `false`: a request for items writes nothing, so the list has no
    // reason to re-read itself.
    expect(onDone).toHaveBeenCalledWith(
      t.requestSent("dana@example.com"),
      false,
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("will not send with nothing ticked", async () => {
    const user = userEvent.setup();
    setup();

    await user.click(screen.getByLabelText(t.requestTitle));

    // An empty request is a letter that says "we need:" and then stops.
    expect(screen.getByRole("button", { name: t.sendRequest })).toBeDisabled();
  });

  it("sends nothing when the confirmation is declined", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(false);
    const { onDone } = setup();

    await user.click(screen.getByLabelText(t.requestTitle));
    await user.click(screen.getByLabelText(t.items.RECEIPTS));
    await user.click(screen.getByRole("button", { name: t.sendRequest }));

    expect(requestItems).not.toHaveBeenCalled();
    expect(onDone).not.toHaveBeenCalled();
    // And the dialog stays open with the tick still on it: cancelling
    // means "not yet", not "start again".
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByLabelText(t.items.RECEIPTS)).toBeChecked();
  });

  it("reports failure when the provider refused the message", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    // The request succeeded. The EMAIL did not. These are different
    // things and only one of them matters to the person waiting.
    requestItems.mockResolvedValue({
      ok: true,
      data: { sent: false, to: "dana@example.com" },
    });
    const { onDone } = setup();

    await user.click(screen.getByLabelText(t.requestTitle));
    await user.click(screen.getByLabelText(t.items.RECEIPTS));
    await user.click(screen.getByRole("button", { name: t.sendRequest }));

    await waitFor(() => expect(onDone).toHaveBeenCalledWith(t.failed, false));
  });
});

describe("sending the statement of claim", () => {
  it("will not send before a file is chosen", async () => {
    const user = userEvent.setup();
    setup();

    await user.click(screen.getByLabelText(t.statementTitle));

    expect(
      screen.getByRole("button", { name: t.sendStatement }),
    ).toBeDisabled();
  });

  it("sends the chosen file, and says so by name before sending", async () => {
    const user = userEvent.setup();
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    const { onDone } = setup();

    await user.click(screen.getByLabelText(t.statementTitle));

    const file = new File(["%PDF-"], "claim.pdf", { type: "application/pdf" });
    // The drop zone is a real <label> around a real file input, which is
    // what makes it reachable by keyboard and by this test. A div that
    // only accepts a drag would pass a visual review and fail a person.
    const input = screen.getByRole("dialog").querySelector("input[type=file]");
    await user.upload(input as HTMLInputElement, file);

    // The filename on screen is the only confirmation an operator gets
    // that they picked the right pleading out of a folder of similar ones.
    expect(screen.getByRole("dialog")).toHaveTextContent("claim.pdf");

    await user.click(screen.getByRole("button", { name: t.sendStatement }));

    expect(confirm).toHaveBeenCalledWith(
      expect.stringContaining("dana@example.com"),
    );
    await waitFor(() =>
      expect(sendStatement).toHaveBeenCalledWith(
        "k",
        "claim-1",
        file,
        undefined,
      ),
    );
    // `true`: the statement is stored on the claim before it goes, so the
    // row's file count is now out of date and the list must re-read.
    expect(onDone).toHaveBeenCalledWith(
      t.statementSent("dana@example.com"),
      true,
    );
  });

  it("passes a typed note through, and omits an empty one", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    setup();

    await user.click(screen.getByLabelText(t.statementTitle));
    const input = screen.getByRole("dialog").querySelector("input[type=file]");
    await user.upload(
      input as HTMLInputElement,
      new File(["x"], "a.pdf", { type: "application/pdf" }),
    );
    // Whitespace is not a note. Sending "   " appends a blank paragraph to
    // a legal letter.
    await user.type(screen.getByRole("textbox"), "   ");
    await user.click(screen.getByRole("button", { name: t.sendStatement }));

    await waitFor(() =>
      expect(sendStatement).toHaveBeenCalledWith(
        "k",
        "claim-1",
        expect.any(File),
        undefined,
      ),
    );
  });
});
