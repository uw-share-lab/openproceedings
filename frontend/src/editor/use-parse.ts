"use client";

/**
 * `/parse` as TanStack queries keyed `["parse", q, mode]` (nextjs-conventions §TanStack Query; design §Data
 * flow). The draft's is debounced 250 ms (spec 05 §Components 1). A newer key cancels the older request (the
 * query function hands its `AbortSignal` to fetch), and an answer is only ever stored under the key it was
 * asked for, so a slow answer for an older draft is never shown for a newer one.
 */
import { keepPreviousData, queryOptions, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import type { Api } from "@/api/client";
import { useApi } from "@/components/providers";
import type { Mode } from "@/lib/search-state";
import { postParse, type ParseOutcome } from "./parse";

export const PARSE_DEBOUNCE_MS = 250;

export function parseQuery(api: Api, q: string, mode: Mode) {
  return queryOptions({
    queryKey: ["parse", q, mode] as const,
    queryFn: ({ signal }) => postParse(api, q, mode, signal),
    // A parse answer is fixed for a (q, mode); a failed one (busy, unreachable) is asked again when needed.
    staleTime: (query) => (query.state.data?.kind === "parsed" ? Infinity : 0),
  });
}

/** Whether there is anything to parse: an empty editor gets no "nothing to search" error. */
const blank = (q: string) => q.trim() === "";

/** `(text, mode)` once it has stopped changing for `ms`. */
function useSettled(text: string, mode: Mode, ms: number): { text: string; mode: Mode } {
  const [settled, setSettled] = useState({ text, mode });
  useEffect(() => {
    const timer = setTimeout(() => setSettled({ text, mode }), ms);
    return () => clearTimeout(timer);
  }, [text, mode, ms]);
  return settled;
}

/**
 * The latest `/parse` answer for the draft: `outcome.q`/`outcome.mode` say which draft it belongs to (while
 * a newer one is in flight, the previous answer stays, so nothing flashes). `null` for a blank draft.
 */
export function useDraftParse(
  text: string,
  mode: Mode,
): { outcome: ParseOutcome | null; refetch: () => void } {
  const api = useApi();
  const settled = useSettled(text, mode, PARSE_DEBOUNCE_MS);
  const query = useQuery({
    ...parseQuery(api, settled.text, settled.mode),
    enabled: !blank(settled.text),
    placeholderData: keepPreviousData,
  });
  const outcome = blank(settled.text) || blank(text) ? null : (query.data ?? null);
  return { outcome, refetch: () => void query.refetch() };
}

/** The `/parse` answer for the searched `(q, mode)` (the sidebar's clauses and the "Searched query" line). */
export function useSearchedParse(q: string, mode: Mode): ParseOutcome | null {
  const api = useApi();
  const query = useQuery({ ...parseQuery(api, q, mode), enabled: !blank(q) });
  return blank(q) ? null : (query.data ?? null);
}
