import type { NextConfig } from "next";

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
  allowedDevOrigins: ["127.0.0.1", "localhost"],
};

export default nextConfig;
