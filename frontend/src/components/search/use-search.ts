"use client";

/**
 * `GET /search` as a TanStack query keyed `["search", q, mode, sort, page]` (nextjs-conventions §TanStack
 * Query; design §Data flow), with `keepPreviousData` so the list never flashes (W4). The answer carries the
 * state it was asked for: while a newer one is in flight the previous answer stays, and the caller can tell
 * the two apart. Nothing is retried on its own (spec 05 §Error handling): `refetch` is the reader's Retry.
 */
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import type { MethodResponse } from "openapi-fetch";
import type { Api } from "@/api/client";
import { outcomeOf, type Outcome } from "@/api/outcome";
import { useApi } from "@/components/providers";
import { toSearchRequest, type SearchState } from "@/lib/search-state";

/** `/search`'s 200 body as the typed client returns it (spans are `number[]`; see nextjs-conventions). */
export type SearchResponse = MethodResponse<Api, "get", "/api/v1/search">;
export type SearchHit = SearchResponse["hits"][number];

export type SearchOutcome = Outcome<SearchResponse> & { readonly state: SearchState };

export async function getSearch(api: Api, state: SearchState, signal?: AbortSignal): Promise<SearchOutcome> {
  const outcome = await outcomeOf(
    () =>
      api.GET("/api/v1/search", {
        params: { query: toSearchRequest(state) },
        ...(signal === undefined ? {} : { signal }),
      }),
    signal,
  );
  return { ...outcome, state };
}

/** The same search (all four URL parts): what an answer is keyed by. */
export function sameSearch(a: SearchState, b: SearchState): boolean {
  return a.q === b.q && a.mode === b.mode && a.sort === b.sort && a.page === b.page;
}

export function useSearch(state: SearchState): {
  /** The latest answer: for `state` once it lands, the previous search's while it is in flight. */
  outcome: SearchOutcome | null;
  fetching: boolean;
  refetch: () => void;
} {
  const api = useApi();
  const query = useQuery({
    queryKey: ["search", state.q, state.mode, state.sort, state.page] as const,
    queryFn: ({ signal }) => getSearch(api, state, signal),
    enabled: state.q.trim() !== "",
    placeholderData: keepPreviousData,
    // An answer is kept for the session (Back shows it again, unchanged); a failed one is asked again.
    staleTime: (query) => (query.state.data?.kind === "ok" ? Infinity : 0),
  });
  return {
    outcome: state.q.trim() === "" ? null : (query.data ?? null),
    fetching: query.isFetching,
    refetch: () => void query.refetch(),
  };
}
