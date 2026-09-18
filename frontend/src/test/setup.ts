import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  window.localStorage.clear();
});

/**
 * jsdom implements neither of these, and both are used deliberately by the
 * components under test -- the wizard scrolls to the top on every step change.
 * Without stubs the tests fail on the browser API rather than on the
 * behaviour, which teaches nobody anything.
 */
window.scrollTo = vi.fn() as unknown as typeof window.scrollTo;
Element.prototype.scrollIntoView = vi.fn();
