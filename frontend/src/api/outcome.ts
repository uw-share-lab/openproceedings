/**
 * Every GET answer as data (spec 05 §Error handling): a 2xx body, or why there is none. `/search` and
 * `/papers/{id}` render each case differently (design W6–W10, P4, P5), so nothing here is thrown except an
 * abort (the caller cancelled it: its key moved on).
 */
import { isErrorEnvelope, type ErrorEnvelope } from "@/editor/parse";

export type Failure =
  /** A JSON error envelope: 422 (diagnostics), 429 `API_RATE_LIMITED`, 503 `API_BUSY`, 500 `API_INTERNAL`, … */
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
  | { readonly kind: "unreachable" };

export type Outcome<T> = { readonly kind: "ok"; readonly data: T } | Failure;

export function retryAfterSeconds(response: Response): number | null {
  const raw = response.headers.get("Retry-After");
  if (raw === null || !/^[0-9]+$/.test(raw.trim())) return null;
  return Number(raw.trim());
}

/** Run one typed-client call and classify its answer. */
export async function outcomeOf<T>(
  run: () => Promise<{ data?: T; error?: unknown; response: Response }>,
  signal?: AbortSignal,
): Promise<Outcome<T>> {
  try {
    const { data, error, response } = await run();
    if (data !== undefined) return { kind: "ok", data };
    const body: unknown = error;
    if (!isErrorEnvelope(body)) return { kind: "no_answer", status: response.status };
    return {
      kind: "refused",
      status: response.status,
      error: body.error,
      retryAfter: retryAfterSeconds(response),
    };
  } catch (e) {
    if (signal?.aborted) throw e;
    // a 2xx whose body isn't JSON fails to parse; anything else is a fetch that never got an answer
    return e instanceof SyntaxError ? { kind: "no_answer", status: null } : { kind: "unreachable" };
  }
}
