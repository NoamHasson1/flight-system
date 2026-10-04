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

import { strings } from "@/lib/strings";

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
  /**
   * The key was missing, wrong, or not configured on the server.
   *
   * Its own case because it used to fall through to `unreachable`, so a
   * rejected admin key and a dead backend produced the identical
   * sentence -- "we could not load the list" -- and an operator had no
   * way to tell "sign in again" from "the server is down".
   */
  | { kind: "denied" }
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

  if (response.status === 401 || response.status === 403) {
    return { ok: false, failure: { kind: "denied" } };
  }

  if (response.status === 503) {
    // The admin API answers 503 when no key is configured at all. From
    // the caller's side that is the same problem as a wrong key: the
    // door is shut and the fix involves a key.
    return { ok: false, failure: { kind: "denied" } };
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
/**
 * Turn FastAPI's validation errors into sentences a customer can act on.
 *
 * This used to keep `msg` and throw `loc` away, which produced
 *
 *     String should have at most 20 characters
 *
 * in English, in the middle of a Hebrew form, on the costs step, about a
 * booking reference typed three steps earlier. A customer cannot fix that:
 * it does not say which field, and it is not in their language.
 *
 * `loc` is the field path, and the last segment is the field itself
 * (`["body", "passengers", 0, "full_name"]`). Naming it is most of the
 * repair. Pydantic's own wording is then translated where it is one of the
 * handful of constraints we actually set, and passed through otherwise --
 * an untranslated sentence after the right field name is still useful,
 * while a translation that guesses at an unfamiliar message is not.
 */
async function validationMessages(response: Response): Promise<string[]> {
  try {
    const body = (await response.json()) as {
      detail?: Array<{ msg?: string; loc?: Array<string | number> }> | string;
    };
    if (typeof body.detail === "string") return [body.detail];
    if (!Array.isArray(body.detail)) return [];
    return body.detail.map(describeValidationError).filter(Boolean);
  } catch {
    return [];
  }
}

function describeValidationError(d: {
  msg?: string;
  loc?: Array<string | number>;
}): string {
  const raw = (d.msg ?? "").replace(/^Value error,\s*/, "").trim();
  if (!raw) return "";

  // The last string in `loc` is the field. Numbers are list indices, and
  // "body" is the envelope -- neither is a field name.
  const key = [...(d.loc ?? [])]
    .reverse()
    .find((part): part is string => typeof part === "string" && part !== "body");
  const field = (key && strings.errors.fieldNames[key]) || "";

  const tooLong = raw.match(/at most (\d+) characters/);
  if (tooLong && field) return strings.errors.tooLong(field, Number(tooLong[1]));

  return field ? `${field}: ${raw}` : raw;
}


/**
 * Exported for tests only.
 *
 * `describeValidationError` is the piece that failed in front of a
 * customer, so it is worth testing directly rather than through a mocked
 * fetch -- the interesting input is the shape of FastAPI's `detail`, and
 * going through the network layer to construct it would obscure that.
 */
export const __testing = { describeValidationError };

// --- the operator's screen ---------------------------------------------------
//
// Separate from everything above because the auth model is different: every
// call carries a shared secret the operator types in, and none of these are
// ever reached by a customer.
//
// THE KEY IS NEVER PUT IN A URL. It travels as a header, so it does not land
// in the Next.js proxy's logs, Render's request logs, or the operator's own
// browser history. That constraint is what makes downloading a document
// awkward -- a browser cannot put a header on an `<a href>` -- and the
// awkwardness is worth it: the alternative leaves links to passport scans
// sitting in three logs.

export type CustomerRow = components["schemas"]["CustomerRow"];
export type CustomerDetail = components["schemas"]["CustomerDetail"];
export type CustomerPage = components["schemas"]["Page_CustomerRow_"];
export type CustomerCounts = components["schemas"]["CustomerCounts"];
export type ArchivedFlight = components["schemas"]["ArchivedFlightOut"];
export type ArchivedFlightPage = components["schemas"]["ArchivedFlightPage"];
export type ClaimStatus =
  | "DRAFT"
  | "SUBMITTED"
  | "IN_REVIEW"
  | "SENT_TO_AIRLINE"
  | "AWAITING_AIRLINE"
  | "SETTLED"
  | "REJECTED"
  | "WITHDRAWN";

export type CustomerQuery = {
  search?: string;
  verdict?: string;
  hasClaim?: boolean;
  includeAnonymous?: boolean;
  hidden?: boolean;
  limit?: number;
  offset?: number;
};

export async function listCustomers(
  key: string,
  query: CustomerQuery = {},
): Promise<ApiResult<CustomerPage>> {
  const params = new URLSearchParams();
  if (query.search) params.set("search", query.search);
  if (query.verdict) params.set("verdict", query.verdict);
  if (query.hasClaim !== undefined) params.set("has_claim", String(query.hasClaim));
  if (query.includeAnonymous) params.set("include_anonymous", "true");
  if (query.hidden) params.set("hidden", "true");
  params.set("limit", String(query.limit ?? 50));
  params.set("offset", String(query.offset ?? 0));

  return request<CustomerPage>(`/api/v1/admin/customers?${params}`, {
    method: "GET",
    headers: adminHeaders(key),
    cache: "no-store",
  });
}

/**
 * The four counters above the list.
 *
 * A separate call from the list, and deliberately not recomputed on every
 * keystroke: these are what the filters narrow FROM, so they do not change
 * when the operator types. Folding them into the page response would make
 * the search re-count the whole table on each character.
 */
export async function customerStats(
  key: string,
  includeAnonymous = false,
): Promise<ApiResult<CustomerCounts>> {
  const params = new URLSearchParams();
  if (includeAnonymous) params.set("include_anonymous", "true");
  return request<CustomerCounts>(`/api/v1/admin/customers/stats?${params}`, {
    method: "GET",
    headers: adminHeaders(key),
    cache: "no-store",
  });
}

export async function readCustomer(
  key: string,
  checkId: string,
): Promise<ApiResult<CustomerDetail>> {
  return request<CustomerDetail>(
    `/api/v1/admin/customers/${encodeURIComponent(checkId)}`,
    { method: "GET", headers: adminHeaders(key), cache: "no-store" },
  );
}

/**
 * Fetch a document and hand the bytes to the browser as a download.
 *
 * Done in JavaScript rather than with a link because the key is a header.
 * The blob URL is revoked immediately afterwards -- it is a live handle to
 * a customer's document inside the page, and leaving it alive means every
 * document an operator opens in a session stays reachable from the tab.
 */
export async function downloadDocument(
  key: string,
  documentId: string,
  filename: string,
): Promise<ApiResult<null>> {
  let response: Response;
  try {
    response = await fetch(
      `/api/v1/admin/documents/${encodeURIComponent(documentId)}`,
      { headers: adminHeaders(key), cache: "no-store" },
    );
  } catch {
    return { ok: false, failure: { kind: "unreachable" } };
  }

  if (response.status === 401 || response.status === 403) {
    return { ok: false, failure: { kind: "refused", message: strings.admin.badKey } };
  }
  if (response.status === 410) {
    return { ok: false, failure: { kind: "refused", message: strings.admin.fileGone } };
  }
  if (!response.ok) return { ok: false, failure: { kind: "unreachable" } };

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
  return { ok: true, data: null };
}

/**
 * Hide customers, or put them back.
 *
 * Named for what it does rather than for the button that calls it. The
 * screen says "delete" because that is what an operator means; nothing is
 * destroyed, which is what makes the undo in the toast possible at all.
 *
 * Returns how many rows actually MOVED, not how many were asked for -- if
 * six of fifty were already hidden, the toast should say 44.
 */
export async function setCustomersHidden(
  key: string,
  checkIds: string[],
  hidden: boolean,
): Promise<ApiResult<{ moved: number }>> {
  return request<{ moved: number }>(
    `/api/v1/admin/customers/${hidden ? "hide" : "restore"}`,
    {
      method: "POST",
      headers: { ...adminHeaders(key), "Content-Type": "application/json" },
      body: JSON.stringify({ check_ids: checkIds }),
    },
  );
}

export async function setClaimStatus(
  key: string,
  claimId: string,
  status: ClaimStatus,
): Promise<ApiResult<{ status: string }>> {
  return request<{ status: string }>(
    `/api/v1/admin/claims/${encodeURIComponent(claimId)}/status`,
    {
      method: "PATCH",
      headers: { ...adminHeaders(key), "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    },
  );
}

/**
 * Fetch a document as an object URL, for showing it rather than saving it.
 *
 * The bytes need the admin key, which a browser cannot put on an `<img
 * src>` -- so the image is fetched here and handed to the DOM as a blob.
 *
 * THE CALLER MUST REVOKE IT. Each URL is a live handle to a customer's
 * document held in the tab; leaving them alive means every receipt an
 * operator glances at stays in memory and reachable for the whole session.
 */
export type DocumentFetch =
  | { ok: true; url: string }
  /** The row exists and the bytes do not. A real, specific answer. */
  | { ok: false; reason: "gone" }
  | { ok: false; reason: "error" };

export async function documentObjectUrl(
  key: string,
  documentId: string,
): Promise<DocumentFetch> {
  try {
    const response = await fetch(
      `/api/v1/admin/documents/${encodeURIComponent(documentId)}`,
      { headers: adminHeaders(key), cache: "no-store" },
    );
    // 410 is the backend saying the record exists and the file does not.
    // Distinguished from every other failure because it is the one with a
    // cause the operator can be told: the bytes are not coming back, and
    // the customer has to be asked to upload it again.
    if (response.status === 410) return { ok: false, reason: "gone" };
    if (!response.ok) return { ok: false, reason: "error" };
    return { ok: true, url: URL.createObjectURL(await response.blob()) };
  } catch {
    return { ok: false, reason: "error" };
  }
}

/**
 * What the archive holds about a flight.
 *
 * The browser version of `app.tasks.find`, which has settled every data
 * argument in this project. A flight number searches all of time because
 * the person asking rarely knows the date; without one the search is
 * bounded by dates, because the server has to decode every stored payload
 * to know whether a flight was disrupted.
 */
export async function searchArchive(
  key: string,
  query: {
    number?: string;
    date?: string;
    since?: string;
    until?: string;
    disruptedOnly?: boolean;
    limit?: number;
    offset?: number;
  },
): Promise<ApiResult<ArchivedFlightPage>> {
  const params = new URLSearchParams();
  if (query.number) params.set("number", query.number);
  if (query.date) params.set("date", query.date);
  if (query.since) params.set("since", query.since);
  if (query.until) params.set("until", query.until);
  if (query.disruptedOnly) params.set("disrupted_only", "true");
  params.set("limit", String(query.limit ?? 100));
  params.set("offset", String(query.offset ?? 0));

  return request<ArchivedFlightPage>(`/api/v1/admin/flights?${params}`, {
    method: "GET",
    headers: adminHeaders(key),
    cache: "no-store",
  });
}

/**
 * Send the lawyer's pleading to the customer, with a copy kept on file.
 *
 * Multipart, so the file goes straight from the operator's machine to
 * the customer's inbox without a round trip through storage in between.
 */
export async function sendStatement(
  key: string,
  claimId: string,
  file: File,
  note?: string,
): Promise<ApiResult<{ sent: boolean; to: string }>> {
  const form = new FormData();
  form.append("file", file);
  if (note) form.append("note", note);

  // No Content-Type header: the browser must set it so it can add the
  // multipart boundary. Setting it by hand produces a body the server
  // cannot parse, and the error says nothing useful.
  return request<{ sent: boolean; to: string }>(
    `/api/v1/admin/claims/${encodeURIComponent(claimId)}/statement`,
    { method: "POST", headers: adminHeaders(key), body: form },
  );
}

export async function requestItems(
  key: string,
  claimId: string,
  items: string[],
  note?: string,
): Promise<ApiResult<{ sent: boolean; to: string }>> {
  return request<{ sent: boolean; to: string }>(
    `/api/v1/admin/claims/${encodeURIComponent(claimId)}/request-items`,
    {
      method: "POST",
      headers: { ...adminHeaders(key), "Content-Type": "application/json" },
      body: JSON.stringify({ items, note: note || null }),
    },
  );
}

function adminHeaders(key: string): Record<string, string> {
  return { "X-Admin-Key": key };
}
