import os from "node:os";

import type { NextConfig } from "next";

// BACKEND_ORIGIN is deliberately NOT read here any more.
//
// `rewrites()` is evaluated at BUILD time and frozen into the output; with
// `output: "standalone"` this file is not even shipped, so a value set at
// deploy time did nothing and the container proxied to its own localhost. The
// proxy is a route handler instead -- src/app/api/[...path]/route.ts -- which
// reads the environment when the request arrives.

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
   * Bundle the server and only the dependencies it actually uses, so the
   * runtime image does not carry node_modules.
   *
   * Without this the image ships every development dependency -- typescript,
   * vitest, playwright's browsers -- to run a server that needs none of them.
   */
  output: "standalone",

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

};

export default nextConfig;
