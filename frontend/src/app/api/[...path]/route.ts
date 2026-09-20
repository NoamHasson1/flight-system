/**
 * The proxy to the backend.
 *
 * WHY THIS IS A ROUTE HANDLER AND NOT A REWRITE
 * ---------------------------------------------
 * It was a rewrite in next.config.ts, which is simpler and cheaper -- no
 * JavaScript in the request path at all. It is also wrong for a container.
 *
 * Next evaluates `rewrites()` at BUILD time and freezes the result into
 * `.next/required-server-files.json`; with `output: "standalone"` the config
 * file is not even shipped. So `BACKEND_ORIGIN` set at deploy time did
 * nothing, and the image happily proxied to 127.0.0.1:8010 -- localhost inside
 * the container, where there is no backend. It failed the same way in every
 * environment and would have looked like a networking problem.
 *
 * A route handler reads the environment when the request arrives, so one image
 * runs in staging and production with nothing but a variable changed. That is
 * worth a few milliseconds of Node.
 *
 * WHAT IT IS FOR
 * --------------
 * The browser talks only to the server that served it. No CORS, and no machine
 * address baked into the client bundle -- so the app works from localhost, a
 * LAN address or a domain with no configuration at all.
 */

import { type NextRequest, NextResponse } from "next/server";

const BACKEND = (
  process.env.BACKEND_ORIGIN ?? "http://127.0.0.1:8010"
).replace(/\/$/, "");

/**
 * Headers that describe the CONNECTION rather than the message, and would be
 * lies about the new one. `host` in particular: forwarding the browser's host
 * makes the backend see a request for the frontend's domain.
 */
const STRIP = new Set([
  "host",
  "connection",
  "keep-alive",
  "transfer-encoding",
  "upgrade",
  "content-length", // recomputed from the body we actually send
]);

async function proxy(request: NextRequest, path: string[]): Promise<Response> {
  const target = `${BACKEND}/api/${path.join("/")}${request.nextUrl.search}`;

  const headers = new Headers();
  request.headers.forEach((value, key) => {
    if (!STRIP.has(key.toLowerCase())) headers.set(key, value);
  });

  // Buffered rather than streamed: a streaming body needs `duplex: "half"`,
  // which is not supported everywhere this might run, and the largest thing
  // that passes through here is a photographed receipt.
  const body =
    request.method === "GET" || request.method === "HEAD"
      ? undefined
      : await request.arrayBuffer();

  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: request.method,
      headers,
      body,
      redirect: "manual",
      cache: "no-store",
    });
  } catch {
    // The backend is unreachable. 502 and not 500: this server is fine, the
    // one behind it is not, and the distinction is what tells whoever is on
    // call which thing to look at. The message is deliberately vague -- the
    // customer-facing copy for an unreachable backend lives in the app, and
    // says explicitly that it means nothing about their flight.
    return NextResponse.json(
      { detail: "The service is temporarily unavailable." },
      { status: 502 },
    );
  }

  // Content-Encoding and Content-Length describe a body fetch has already
  // decoded; passing them on makes the browser try to decode it twice.
  const out = new Headers(upstream.headers);
  out.delete("content-encoding");
  out.delete("content-length");
  out.delete("transfer-encoding");

  return new NextResponse(upstream.body, { status: upstream.status, headers: out });
}

type Context = { params: Promise<{ path: string[] }> };

async function handler(request: NextRequest, context: Context): Promise<Response> {
  const { path } = await context.params;
  return proxy(request, path);
}

export const GET = handler;
export const POST = handler;
export const PUT = handler;
export const PATCH = handler;
export const DELETE = handler;

// Nothing here may be cached or prerendered: every response is about one
// person's flight.
export const dynamic = "force-dynamic";
