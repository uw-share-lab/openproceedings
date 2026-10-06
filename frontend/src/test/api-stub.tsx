/**
 * Test helpers: a stubbed API behind the real typed client (no network, testing-standards), the providers
 * around a component, and what CodeMirror needs from the DOM that jsdom leaves out.
 */
import type { QueryClient } from "@tanstack/react-query";
import { act, render, type RenderResult } from "@testing-library/react";
import type { ReactNode } from "react";
import { vi } from "vitest";
import { createApi, type Schemas } from "@/api/client";
import { newQueryClient, Providers } from "@/components/providers";

export interface Call {
  readonly method: string;
  readonly path: string;
  /** The request's query parameters (GET /search, /papers/{id}). */
  readonly query: URLSearchParams;
  /** A JSON body parsed; any other body (a RIS file, `POST /compare`) as its text; `null` without one. */
  readonly body: unknown;
  readonly contentType: string | null;
  readonly signal: AbortSignal;
}

export type Handler = (call: Call) => Response | Promise<Response>;

export function json(body: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

/** A fetch that answers from `handler`, recording each call; a call whose signal aborts rejects like fetch. */
export function stubFetch(handler: Handler): { fetch: typeof globalThis.fetch; calls: Call[] } {
  const calls: Call[] = [];
  const fetchImpl: typeof globalThis.fetch = async (input) => {
    if (!(input instanceof Request)) throw new Error("the typed client always passes a Request");
    const url = new URL(input.url);
    const text = input.method === "GET" ? "" : await input.text();
    const contentType = input.headers.get("Content-Type");
    const isJson = contentType === null || contentType.startsWith("application/json");
    const call: Call = {
      method: input.method,
      path: url.pathname,
      query: url.searchParams,
      body: text === "" ? null : isJson ? JSON.parse(text) : text,
      contentType,
      signal: input.signal,
    };
    calls.push(call);
    const answer = Promise.resolve(handler(call));
    return new Promise<Response>((resolve, reject) => {
      const abort = () => reject(new DOMException("The operation was aborted.", "AbortError"));
      if (input.signal.aborted) abort();
      input.signal.addEventListener("abort", abort);
      answer.then(resolve, reject);
    });
  };
  return { fetch: fetchImpl, calls };
}

export function renderWithApi(
  ui: ReactNode,
  handler: Handler,
): RenderResult & { calls: Call[]; queryClient: QueryClient } {
  const { fetch, calls } = stubFetch(handler);
  const queryClient = newQueryClient();
  const api = createApi("http://api.test", fetch);
  const result = render(ui, {
    wrapper: ({ children }) => (
      <Providers api={api} queryClient={queryClient}>
        {children}
      </Providers>
    ),
  });
  return { ...result, calls, queryClient };
}

type ParseResponse = Schemas["ParseResponse"];

/** A `/parse` answer with no diagnostics; override what a test needs. */
export function parsed(q: string, over: Partial<ParseResponse> = {}): ParseResponse {
  return {
    ast: { kind: "term", field: null, token: q, span: [0, [...q].length] },
    effective_ast: {
      kind: "and",
      span: [0, [...q].length],
      children: [
        { kind: "term", field: null, token: q, span: [0, [...q].length] },
        {
          kind: "filter",
          field: "track",
          values: ["datasets_benchmarks", "main", "position"],
          span: [[...q].length, [...q].length],
        },
        { kind: "filter", field: "status", values: ["accepted"], span: [[...q].length, [...q].length] },
      ],
    },
    canonical: `${q} AND track:(datasets_benchmarks OR main OR position) AND status:accepted`,
    canonical_hash: "h",
    defaults: ["track", "status"],
    errors: [],
    warnings: [],
    translations: [],
    filters: null,
    word_forms: [],
    word_forms_skipped: [],
    identification_query: q,
    index_version: "idx1",
    mode: "native",
    query_version: "q1",
    tokenizer_version: "t1",
    ...over,
  };
}

export const META: Schemas["MetaResponse"] = {
  filter_fields: ["venue", "year", "track", "status"],
  text_fields: ["title", "abstract"],
  index_version: "a1b2c3d4e5f6",
  index_versions: ["a1b2c3d4e5f6"],
  limits: {
    max_query_length: 2000,
    max_query_depth: 64,
    max_verification_candidates: 1,
    max_verified_clauses: 1,
    max_counted_groups: 10,
    max_counted_terms: 5000,
    max_counted_ids: 300000,
    compare: null,
  },
  query_version: "q1",
  tokenizer_version: "t1",
  values: {
    venue: ["NeurIPS", "ICLR", "ICML"],
    track: ["main", "datasets_benchmarks", "position", "workshop"],
    status: ["accepted", "rejected"],
  },
};

/** jsdom has no layout: CodeMirror measures ranges, which jsdom doesn't implement. */
export function polyfillLayout(): void {
  const rect = { x: 0, y: 0, width: 0, height: 0, top: 0, left: 0, right: 0, bottom: 0, toJSON: () => ({}) };
  const rects = Object.assign([], { item: () => null });
  Range.prototype.getBoundingClientRect = () => rect;
  Range.prototype.getClientRects = () => rects;
  Element.prototype.scrollIntoView = () => {};
}

/**
 * Under fake timers: let `ms` pass, then let what that released finish. React renders a state update at the
 * end of each `act`, and a stubbed fetch reads its request body on the real event loop, so this runs several
 * short `act`s, each a real turn followed by the fake zero-delay timers it queued (TanStack Query's
 * notifications).
 */
export async function pass(ms = 0): Promise<void> {
  await act(() => vi.advanceTimersByTimeAsync(ms));
  for (let turn = 0; turn < 8; turn++) {
    await act(async () => {
      await new Promise((resolve) => realSetTimeout(resolve, 0));
      await vi.advanceTimersByTimeAsync(0);
    });
  }
}

/** The real `setTimeout`, taken before any test fakes it. */
const realSetTimeout = globalThis.setTimeout;
