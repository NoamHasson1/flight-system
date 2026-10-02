/**
 * Where the backend is, given whatever the host has put in the environment.
 *
 * ONE RULE, ONE PLACE. The proxy and the server-side client both need it, and
 * when it lived in both they drifted -- which is how a scheme-less hostname
 * shipped twice.
 *
 * WHAT RENDER ACTUALLY HANDS OVER, AND WHY IT CHANGED
 * ---------------------------------------------------
 * `fromService: property: host` renders differently depending on the plan:
 *
 *     free   flight-backend-vzuh.onrender.com    the PUBLIC host
 *     paid   flight-backend-vzuh                 the PRIVATE host
 *
 * Paid services get a private network; free ones have none, so there is
 * nothing internal to name. Upgrading therefore changed the value of an
 * environment variable nobody edited, and every request from the frontend
 * died at DNS -- in 0.3 seconds, which reads as "the backend is down" and is
 * in fact "the backend is somewhere else now".
 *
 * Neither form carries a scheme, and fetch rejects a URL without one.
 *
 * THE RULE
 * --------
 * A dot in the hostname means a public address, which is https. No dot means
 * a private one, which is plain http -- Render terminates TLS at the edge and
 * the private network is inside it, so https to an internal name is talking
 * TLS to a server that is not speaking it.
 *
 * That test is on the HOSTNAME only: `flight-backend-vzuh:8000` has no dot
 * and is internal, while the port would otherwise confuse a naive check.
 */
export function resolveBackendOrigin(
  configured: string | undefined,
  fallback = "http://127.0.0.1:8010",
): string {
  const raw = (configured ?? fallback).trim();
  if (!raw) return fallback;
  if (/^https?:\/\//.test(raw)) return raw.replace(/\/$/, "");

  const hostname = raw.split("/")[0].split(":")[0];
  return `${isLocal(hostname) ? "http" : "https"}://${raw}`.replace(/\/$/, "");
}

/**
 * Hosts that are reached without TLS.
 *
 * The rule used to be "a dot means public means https", which is right for
 * every value Render produces -- `flight-backend-vzuh` has no dot and is
 * private, `flight-backend-vzuh.onrender.com` has dots and is public.
 *
 * IT IS WRONG FOR AN IP ADDRESS. `127.0.0.1` is full of dots and is the
 * least public host there is, so pointing a local frontend at a local
 * backend produced an https request to a plain HTTP server, a failed TLS
 * handshake, and a page saying the service was temporarily unavailable.
 * Nothing in that chain mentions the scheme, which is what made it worth
 * fixing rather than remembering.
 *
 * Loopback and the private IPv4 ranges, plus the usual local names.
 */
function isLocal(hostname: string): boolean {
  if (!hostname.includes(".")) return true;
  if (hostname === "localhost" || hostname.endsWith(".localhost")) return true;
  if (hostname === "[::1]" || hostname === "::1") return true;
  return (
    /^127\./.test(hostname) ||
    /^10\./.test(hostname) ||
    /^192\.168\./.test(hostname) ||
    /^172\.(1[6-9]|2\d|3[01])\./.test(hostname)
  );
}
