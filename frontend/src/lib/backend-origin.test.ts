/**
 * Tests for turning Render's environment into a URL fetch will accept.
 *
 * WHY THIS FILE EXISTS
 * --------------------
 * Upgrading from free to paid plans took the site down. Nobody edited a
 * variable: `fromService: property: host` simply started rendering the
 * PRIVATE hostname instead of the public one, because paid services have a
 * private network and free ones do not. The proxy prefixed https:// to a
 * name that only answers http, and every check returned 502 in 0.3 seconds.
 *
 * The lesson is the reason for the test: THIS VALUE CHANGES SHAPE WHEN
 * SOMETHING OUTSIDE THE CODE CHANGES. So every shape it is known to take is
 * pinned here, with the one it took in production first.
 */

import { describe, expect, it } from "vitest";

import { resolveBackendOrigin } from "./backend-origin";

describe("resolveBackendOrigin", () => {
  it("treats a private hostname as http", () => {
    // The exact value that broke production: Render's paid private host,
    // no dot, no scheme, no port.
    expect(resolveBackendOrigin("flight-backend-vzuh")).toBe(
      "http://flight-backend-vzuh",
    );
  });

  it("treats a private host:port as http, ignoring the port", () => {
    // `property: hostport` on a paid plan. The colon must not be mistaken
    // for structure that makes this look public.
    expect(resolveBackendOrigin("flight-backend-vzuh:8000")).toBe(
      "http://flight-backend-vzuh:8000",
    );
  });

  it("treats a public hostname as https", () => {
    // What the same variable rendered on the free plan.
    expect(resolveBackendOrigin("flight-backend-vzuh.onrender.com")).toBe(
      "https://flight-backend-vzuh.onrender.com",
    );
  });

  it("leaves an explicit scheme alone", () => {
    expect(resolveBackendOrigin("http://127.0.0.1:8010")).toBe(
      "http://127.0.0.1:8010",
    );
    expect(resolveBackendOrigin("https://api.example.com")).toBe(
      "https://api.example.com",
    );
  });

  it("strips a trailing slash, so paths do not double up", () => {
    // `${origin}/api/v1/...` with a trailing slash gives //api, which some
    // routers treat as a different path and others as a redirect.
    expect(resolveBackendOrigin("https://api.example.com/")).toBe(
      "https://api.example.com",
    );
  });

  it("falls back when the variable is missing or blank", () => {
    // Blank as well as undefined: an env var set to "" is a real thing that
    // happens, and it must not produce "http://".
    expect(resolveBackendOrigin(undefined)).toBe("http://127.0.0.1:8010");
    expect(resolveBackendOrigin("")).toBe("http://127.0.0.1:8010");
    expect(resolveBackendOrigin("   ")).toBe("http://127.0.0.1:8010");
  });
});
