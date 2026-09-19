import os from "node:os";

import type { NextConfig } from "next";

/**
 * Where the backend actually listens. Server-side only -- it is never inlined
 * into the browser bundle, which is the point: the browser no longer needs to
 * know, so nothing in the client is tied to one machine's address.
 */
const BACKEND_ORIGIN = process.env.BACKEND_ORIGIN ?? "http://127.0.0.1:8010";

/**
 * Every address this machine answers on, so the dev server accepts a browser
 * that reached it over the local network.
 *
 * Read from the interfaces rather than hardcoded, because a laptop's LAN
 * address is assigned by whatever router it last joined and changes without
 * warning. A literal address here would work in the kitchen and fail in the
 * office, with a symptom -- page renders, nothing is interactive -- that looks
 * nothing like a networking problem.
 */
function localAddresses(): string[] {
  return Object.values(os.networkInterfaces())
    .flat()
    .filter((i) => i && i.family === "IPv4" && !i.internal)
    .map((i) => i!.address);
}

const nextConfig: NextConfig = {
  /**
   * Next 16 blocks cross-origin requests to dev resources by default, and it
   * counts 127.0.0.1 and localhost as different origins. Browsing the dev
   * server on the loopback IP while it serves from localhost silently blocks
   * the HMR and runtime resources, which breaks hydration -- the page renders,
   * the chunks load, and nothing is interactive.
   *
   * The symptom is easy to misread: a form doing a native GET submit instead of
   * running its onSubmit looks exactly like a bug in the component.
   *
   * Development only; it has no effect on a production build.
   */
  allowedDevOrigins: ["127.0.0.1", "localhost", ...localAddresses()],

  /**
   * The browser talks to this server and only this server; this server talks to
   * the backend.
   *
   * The alternative -- the browser calling the backend directly -- needs the
   * backend's absolute address baked into the client bundle at build time. That
   * address is correct for exactly one machine on exactly one network: a laptop
   * on the same Wi-Fi loads the page fine and then sends every request to
   * 127.0.0.1, which is its own machine, where nothing is listening. It also
   * makes every request cross-origin, so CORS has to be widened for each new
   * address.
   *
   * Proxying costs one hop in development and removes both problems: same
   * origin, no CORS, and nothing anywhere that names a specific machine.
   */
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${BACKEND_ORIGIN}/api/:path*` },
    ];
  },
};

export default nextConfig;
