import { defineConfig, devices } from "@playwright/test";

/**
 * One end-to-end run, against real servers.
 *
 * Everything else in this project is tested in isolation and runs in
 * milliseconds. This exists for the failures that only appear when the pieces
 * are joined -- a CORS origin that does not match, a route that 404s, a form
 * posting to the wrong path -- which unit tests structurally cannot see. It is
 * slow, so there is exactly one.
 *
 * `baseURL` is localhost, not 127.0.0.1: Next 16 treats them as different
 * origins and blocks its own dev resources across them, which silently breaks
 * hydration and makes every interactive test fail for a reason that has
 * nothing to do with the code.
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  reporter: process.env.CI ? "list" : [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3111",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
