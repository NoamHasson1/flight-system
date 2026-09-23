/**
 * The typed client for the backend.
 *
 * Types come from `api-types.ts`, which is generated from the backend's own
 * OpenAPI document (`npm run types`). That is the point: the frontend cannot
 * drift from the API, because the contract is generated from the server rather
 * than described twice and kept in sync by hand.
 *
 * The other principle here is inherited from the backend and matters more than
 * the typing: **a failure to reach the API must never be presented as an answer
 * about somebody's flight.** Every function below returns a discriminated
 * result rather than throwing, so a caller has to deal with "we could not ask"
 * as its own case instead of catching an exception and falling through to
 * whatever the happy path renders.
 */

import type { components } from "./api-types";
import { resolveBackendOrigin } from "./backend-origin";

export type EligibilityRequest = components["schemas"]["EligibilityRequest"];
export type EligibilityResponse = components["schemas"]["EligibilityResponse"];
export type Outcome = components["schemas"]["OutcomeOut"];
export type FlightSummary = components["schemas"]["FlightOut"];
export type FlightOption = components["schemas"]["FlightOptionOut"];
export type Money = components["schemas"]["MoneyOut"];

export type ClaimCreate = components["schemas"]["ClaimCreate"];
export type ClaimOut = components["schemas"]["ClaimOut"];
export type PassengerIn = components["schemas"]["PassengerIn"];
export type ExpenseIn = components["schemas"]["ExpenseIn"];
export type DocumentUpload = components["schemas"]["DocumentUploadResponse"];

export type Verdict = "ELIGIBLE" | "NOT_ELIGIBLE" | "NEEDS_REVIEW";
export type CheckStatus = "DECIDED" | "NOT_FOUND" | "AMBIGUOUS" | "UNRESOLVED";

/**
 * Why a call failed, in terms that decide what the customer is shown.
 *
 * `unreachable` covers a dead network, a timeout and a 5xx together, because
 * from the customer's side they are the same event and want the same sentence.
 * `invalid` is the only one that is about something they typed.
 */
export type ApiFailure =
  | { kind: "unreachable" }
  | { kind: "invalid"; messages: string[] }
  | { kind: "notFound" }
  /** The request was understood and refused for a reason worth showing:
      a claim already submitted, a claim with no passengers. */
  | { kind: "refused"; message: string };

export type ApiResult<T> =
  | { ok: true; data: T }
  | { ok: false; failure: ApiFailure };

/**
 * What to put in front of every path.
 *
 * In the browser: nothing. Requests go to the page's own origin and this app
 * proxies `/api/*` onward (see src/app/api/[...path]/route.ts). Whatever
 * address the page was opened on -- localhost, a LAN IP, a domain -- the API
 * is reached at that same address, so it works from another machine with no
 * configuration and no CORS.
 *
 * On the server, where the result screens are rendered: an absolute URL,
 * because fetch on the server has no page origin to be relative to. It is
 * BACKEND_ORIGIN, the same variable the proxy uses -- inside a container
 * 127.0.0.1 is the container itself, and defaulting to it makes every
 * server-rendered page report that the flight database is unreachable while
 * the very same request works from the browser.
 *
 * Read per call rather than once at module load, so a value set at deploy time
 * is honoured rather than whatever was present when the module first ran.
 *
 * NEXT_PUBLIC_API_URL still wins where it is set, for pointing a local
 * frontend at a deployed backend.
 */
function baseUrl(): string {
  const explicit = process.env.NEXT_PUBLIC_API_URL;
  if (explicit) return explicit.replace(/\/$/, "");
  if (typeof window !== "undefined") return "";
  // Same rule as the proxy, from the same place -- when this logic lived in
  // both files they drifted, and a scheme-less hostname shipped twice.
  return resolveBackendOrigin(process.env.BACKEND_ORIGIN);
}

/**
 * How long the browser waits before deciding nothing is coming.
 *
 * THIS IS THE LAST LAYER IN A LADDER, AND IT MUST BE THE MOST PATIENT.
 *
 *     browser (here)   this value
 *     proxy            75s, twice        -- src/app/api/[...path]/route.ts
 *     backend          about 81s worst case:
 *                        board       5s connect + 15s read
 *                        AeroDataBox 3 attempts of the same, plus backoff
 *
 * It was 20 seconds, which is BELOW the budget the backend is allowed to
 * spend. The browser therefore hung up on requests that were going to
 * succeed, and did it first, so the proxy's patience was never reached.
 *
 * Measured cold start on a free host: 21.9s. Two seconds past the old
 * ceiling, which made it fail for essentially every first visitor after a
 * quiet spell -- while showing them a message about the flight database
 * being unreachable, when it was merely still waking up.
 *
 * The board request is the slow one by design: it pulls the WHOLE Ben Gurion
 * board, about 3,200 flights, on every lookup. A slow morning at data.gov.il
 * costs fifteen seconds on a request that works perfectly.
 *
 * So: longer than anything downstream can legitimately take, and short enough
 * that a genuinely dead backend still ends. The waiting is made bearable by
 * saying what is happening -- see CheckForm's `slow` state -- rather than by
 * cutting it short and calling a slow answer a failure.
 */
const TIMEOUT_MS = 90_000;

export async function checkEligibility(
  input: EligibilityRequest,
): Promise<ApiResult<EligibilityResponse>> {
  return request<EligibilityResponse>("/api/v1/eligibility/check", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export async function getCheck(
  checkId: string,
): Promise<ApiResult<EligibilityResponse>> {
  return request<EligibilityResponse>(
    `/api/v1/eligibility/checks/${encodeURIComponent(checkId)}`,
    { method: "GET", cache: "no-store" },
  );
}

export async function createClaim(
  input: ClaimCreate,
): Promise<ApiResult<ClaimOut>> {
  return request<ClaimOut>("/api/v1/claims", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export async function uploadDocument(
  claimId: string,
  file: File,
  kind: string,
  expenseId?: string,
): Promise<ApiResult<DocumentUpload>> {
  const form = new FormData();
  form.append("file", file);
  form.append("kind", kind);
  if (expenseId) form.append("expense_id", expenseId);

  // No Content-Type header: the browser must set it so it can add the
  // multipart boundary. Setting it by hand produces a body the server cannot
  // parse, and the error says nothing useful.
  return request<DocumentUpload>(
    `/api/v1/claims/${encodeURIComponent(claimId)}/documents`,
    { method: "POST", body: form },
  );
}

export async function submitClaim(claimId: string): Promise<ApiResult<ClaimOut>> {
  return request<ClaimOut>(
    `/api/v1/claims/${encodeURIComponent(claimId)}/submit`,
    { method: "POST" },
  );
}

// --- the one place that talks to the network --------------------------------

async function request<T>(
  path: string,
  init: RequestInit,
): Promise<ApiResult<T>> {
  let response: Response;

  try {
    response = await fetch(`${baseUrl()}${path}`, {
      ...init,
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
  } catch {
    // A dead network, a timeout, DNS, CORS. The customer does not care which,
    // and none of them is an answer about their flight.
    return { ok: false, failure: { kind: "unreachable" } };
  }

  if (response.status === 404) {
    return { ok: false, failure: { kind: "notFound" } };
  }

  if (response.status === 409) {
    return {
      ok: false,
      failure: { kind: "refused", message: await detailMessage(response) },
    };
  }

  if (response.status === 422) {
    return {
      ok: false,
      failure: { kind: "invalid", messages: await validationMessages(response) },
    };
  }

  if (!response.ok) {
    return { ok: false, failure: { kind: "unreachable" } };
  }

  try {
    return { ok: true, data: (await response.json()) as T };
  } catch {
    // A 200 whose body will not parse is a broken deployment, not a verdict.
    return { ok: false, failure: { kind: "unreachable" } };
  }
}

/** A plain `detail` string, as the claims endpoints return on a 409. */
async function detailMessage(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: string };
    return typeof body.detail === "string" ? body.detail : "";
  } catch {
    return "";
  }
}

/**
 * Pull readable sentences out of FastAPI's validation payload.
 *
 * Those messages are written for humans in the backend schemas -- "That date is
 * in the future. Enter the date the flight departed" -- so they are worth
 * surfacing rather than replacing with a generic "invalid input". The
 * `Value error, ` prefix Pydantic adds is stripped, because it is noise to
 * everyone who is not a Python developer.
 */
async function validationMessages(response: Response): Promise<string[]> {
  try {
    const body = (await response.json()) as {
      detail?: Array<{ msg?: string }> | string;
    };
    if (typeof body.detail === "string") return [body.detail];
    if (!Array.isArray(body.detail)) return [];
    return body.detail
      .map((d) => (d.msg ?? "").replace(/^Value error,\s*/, "").trim())
      .filter(Boolean);
  } catch {
    return [];
  }
}
