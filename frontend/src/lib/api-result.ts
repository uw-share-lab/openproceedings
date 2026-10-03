/**
 * One API call's outcome as data (nextjs-conventions: every non-2xx answer is data to render, not an
 * exception). `openapi-fetch` gives the spec 04 envelope for a JSON error and the body text for anything else
 * (a proxy's HTML 502), and throws only when no response came back at all.
 */
import type { Schemas } from "@/api/client";

export type ApiFailure =
  /** The API answered with its error envelope (spec 04 §Error handling). */
  | { kind: "api"; status: number; error: Schemas["ErrorBody"]; retryAfter: number | null }
  /** Something other than the API answered (not JSON): a proxy, a restart. */
  | { kind: "server"; status: number }
  /** No answer: offline, DNS, a refused connection. */
  | { kind: "network" };

export type ApiResult<T> = { kind: "ok"; data: T } | ApiFailure;

interface Answer<T> {
  data?: T;
  error?: unknown;
  response: Response;
}

function isEnvelope(value: unknown): value is Schemas["ErrorEnvelope"] {
  if (typeof value !== "object" || value === null || !("error" in value)) return false;
  const body: unknown = value.error;
  return (
    typeof body === "object" &&
    body !== null &&
    "code" in body &&
    typeof body.code === "string" &&
    "message" in body &&
    typeof body.message === "string"
  );
}

/** The `Retry-After` header in whole seconds, or null when absent or not a number of seconds. */
export function retryAfterSeconds(response: Response): number | null {
  const value = response.headers.get("Retry-After");
  if (value === null || !/^\d+$/.test(value.trim())) return null;
  return Number(value.trim());
}

/** Run one typed call and settle it into an `ApiResult`, never throwing. */
export async function settle<T>(call: () => Promise<Answer<T>>): Promise<ApiResult<T>> {
  let answer: Answer<T>;
  try {
    answer = await call();
  } catch {
    return { kind: "network" };
  }
  const { data, error, response } = answer;
  if (response.ok && data !== undefined) return { kind: "ok", data };
  if (isEnvelope(error)) {
    return {
      kind: "api",
      status: response.status,
      error: error.error,
      retryAfter: retryAfterSeconds(response),
    };
  }
  return { kind: "server", status: response.status };
}
