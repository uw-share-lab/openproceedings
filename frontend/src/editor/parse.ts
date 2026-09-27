/**
 * `POST /api/v1/parse` for the editor (spec 04 §Endpoints; spec 05 §Error handling). Every answer becomes a
 * `ParseOutcome`, keyed by the `(q, mode)` it was asked for, so a caller can tell which draft it belongs to and
 * drop it when the draft has moved on. Only an abort is thrown (the caller cancelled it); nothing else is.
 */
import type { MethodResponse } from "openapi-fetch";
import type { Api, Schemas } from "@/api/client";
import type { Mode } from "@/lib/search-state";

/** `/parse`'s 200 body as the typed client returns it (`schema.ts`'s `ParseResponse`, read through the client). */
export type ParseResponse = MethodResponse<Api, "post", "/api/v1/parse">;
export type Diagnostic = ParseResponse["errors"][number];
export type ErrorEnvelope = Schemas["ErrorEnvelope"];

interface Keyed {
  readonly q: string;
  readonly mode: Mode;
}

export type ParseOutcome = Keyed &
  (
    | { readonly kind: "parsed"; readonly result: ParseResponse }
    /** 413 `API_BODY_TOO_LARGE`: the query is far too long to send (only a huge paste reaches it). */
    | { readonly kind: "too_large"; readonly message: string }
    /** Any other JSON error envelope: 429 `API_RATE_LIMITED`, 503 `API_BUSY` / `API_INDEX_NOT_LOADED`, … */
    | {
        readonly kind: "refused";
        readonly status: number;
        readonly error: ErrorEnvelope["error"];
        /** `Retry-After`, in whole seconds, when the server sent one. */
        readonly retryAfter: number | null;
      }
    /** A body that isn't JSON: it came from in front of the app (a proxy, uvicorn's limit), meaning busy. */
    | { readonly kind: "no_answer"; readonly status: number | null }
    /** The request never got an answer (offline, DNS, connection refused). */
    | { readonly kind: "unreachable" }
  );

/** An error body shaped like spec 04's envelope. `openapi-fetch` hands back the raw text for a non-JSON body. */
export function isErrorEnvelope(body: unknown): body is ErrorEnvelope {
  if (typeof body !== "object" || body === null || !("error" in body)) return false;
  const error: unknown = body.error;
  return (
    typeof error === "object" &&
    error !== null &&
    "code" in error &&
    typeof error.code === "string" &&
    "message" in error &&
    typeof error.message === "string"
  );
}

function retryAfter(response: Response): number | null {
  const raw = response.headers.get("Retry-After");
  if (raw === null || !/^[0-9]+$/.test(raw.trim())) return null;
  return Number(raw.trim());
}

export async function postParse(
  api: Api,
  q: string,
  mode: Mode,
  signal?: AbortSignal,
): Promise<ParseOutcome> {
  try {
    const { data, error, response } = await api.POST("/api/v1/parse", {
      body: { q, mode },
      ...(signal === undefined ? {} : { signal }),
    });
    if (data !== undefined) return { q, mode, kind: "parsed", result: data };
    const body: unknown = error;
    if (!isErrorEnvelope(body)) return { q, mode, kind: "no_answer", status: response.status };
    if (response.status === 413) return { q, mode, kind: "too_large", message: body.error.message };
    return {
      q,
      mode,
      kind: "refused",
      status: response.status,
      error: body.error,
      retryAfter: retryAfter(response),
    };
  } catch (e) {
    if (signal?.aborted) throw e; // cancelled: the draft moved on, so no outcome belongs to it
    // a 2xx whose body isn't JSON fails to parse; anything else is a fetch that never got an answer
    return e instanceof SyntaxError
      ? { q, mode, kind: "no_answer", status: null }
      : { q, mode, kind: "unreachable" };
  }
}
