/**
 * Fetching a customer's document for display.
 *
 * WHY THIS IS TESTED AT ALL
 *
 * It returned `string | null`, and the caller rendered "loading…" until a
 * string arrived. So every failure -- a dead backend, a wrong key, a file
 * that no longer exists -- looked identical and looked temporary.
 *
 * It was not temporary. Uploads were written to a path inside the Render
 * container, which is rebuilt from its image on every deploy, so every
 * file a customer had ever sent was gone. The operator saw a spinner,
 * waited, reloaded, waited again, and was never told that the bytes were
 * not coming back and the customer had to be asked for them a second time.
 *
 * The distinction these tests protect is the whole repair: 410 means
 * "gone, ask again", everything else means "try again".
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { documentObjectUrl } from "@/lib/api";

const KEY = "test-key";

/**
 * The shape the code actually reads, not a real `Response`.
 *
 * Constructing a `Response` threw in this environment, and because the
 * function under test catches everything, the throw arrived as
 * `{ok: false, reason: "error"}` -- a test failing for a reason that had
 * nothing to do with the code. A stub that provides exactly `status` and
 * `blob()` cannot fail that way.
 */
function respondWith(status: number) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      status,
      ok: status >= 200 && status < 300,
      blob: async () => ({ size: 1, type: "image/png" }),
    })),
  );
}

// jsdom has no object URLs; the code only needs a string back.
const objectUrl = { createObjectURL: () => "blob:fake", revokeObjectURL: () => {} };

afterEach(() => vi.unstubAllGlobals());

describe("documentObjectUrl", () => {
  it("returns a usable url when the file is there", async () => {
    respondWith(200);
    vi.stubGlobal("URL", objectUrl);

    const result = await documentObjectUrl(KEY, "doc-1");

    expect(result).toEqual({ ok: true, url: "blob:fake" });
  });

  it("reports 410 as GONE, which is the one failure with a cause", async () => {
    /**
     * The backend answers 410 when the row exists and the bytes do not.
     * That is the only failure here an operator can act on -- there is
     * nothing to retry, and the customer has to upload it again -- so it
     * must survive as its own case rather than collapsing into "error".
     */
    respondWith(410);

    const result = await documentObjectUrl(KEY, "doc-1");

    expect(result).toEqual({ ok: false, reason: "gone" });
  });

  it("reports a rejected key as a plain error, not as gone", async () => {
    /**
     * The distinction matters in the wrong direction too. Telling an
     * operator "ask the customer to upload it again" because their key
     * expired would send them to bother somebody over nothing.
     */
    respondWith(401);

    const result = await documentObjectUrl(KEY, "doc-1");

    expect(result).toEqual({ ok: false, reason: "error" });
  });

  it("reports a dead network as an error rather than throwing", async () => {
    /**
     * This runs inside a render loop over every thumbnail. An exception
     * escaping here would take out the whole panel, so the operator would
     * lose the customer's details as well as one image.
     */
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("Failed to fetch");
      }),
    );

    const result = await documentObjectUrl(KEY, "doc-1");

    expect(result).toEqual({ ok: false, reason: "error" });
  });

  it("never resolves to something that reads as still loading", async () => {
    /**
     * The property that was actually broken, stated directly: whatever
     * happens, the caller gets a settled answer it can render. A promise
     * resolving to null was indistinguishable from one that had not
     * resolved yet, and the UI chose the wrong interpretation.
     */
    vi.stubGlobal("URL", objectUrl);
    for (const status of [200, 401, 404, 410, 500]) {
      respondWith(status);
      vi.stubGlobal("URL", objectUrl);
      const result = await documentObjectUrl(KEY, "doc-1");
      expect(result).toHaveProperty("ok");
    }
  });
});
