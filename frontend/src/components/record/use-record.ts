"use client";

/**
 * A search record from the API (spec 04 §Search records; design R1, decision-014). Read in two steps: the
 * stored record first (`GET /records/{id}?replay=false`: one token, answered while every verification slot is
 * taken), then its replay (`GET /records/{id}`, the export weight), so the recorded fields show at once and a
 * 429 or `API_BUSY` on the replay only delays the status. Keys: `["record", id, "stored"]`, `["record", id]`.
 * Nothing retries on its own; `refetch` is the reader's Retry.
 */
import { useQuery } from "@tanstack/react-query";
import type { Api } from "@/api/client";
import { outcomeOf, type Outcome } from "@/api/outcome";
import { useApi } from "@/components/providers";
import { parseQuery } from "@/editor/use-parse";
import type { ParseResponse } from "@/editor/parse";
import type { RecordResponse, SearchRecord } from "@/lib/methods-text";

export type RecordOutcome = Outcome<RecordResponse> | { readonly kind: "not_found" };

export async function getRecord(
  api: Api,
  id: string,
  replay: boolean,
  signal?: AbortSignal,
): Promise<RecordOutcome> {
  const outcome = await outcomeOf(
    () =>
      api.GET("/api/v1/records/{id}", {
        params: { path: { id }, query: replay ? {} : { replay: false } },
        ...(signal === undefined ? {} : { signal }),
      }),
    signal,
  );
  // 404, or 422 API_BAD_PARAM for an id that isn't one (spec 05 §Error handling): the not-found state
  if (
    outcome.kind === "refused" &&
    (outcome.status === 404 || (outcome.status === 422 && outcome.error.code === "API_BAD_PARAM"))
  ) {
    return { kind: "not_found" };
  }
  return outcome;
}

const keep = {
  staleTime: (q: { state: { data?: RecordOutcome | undefined } }) =>
    q.state.data?.kind === "ok" ? Infinity : 0,
};

export function useStoredRecord(id: string): { outcome: RecordOutcome | null; refetch: () => void } {
  const api = useApi();
  const query = useQuery({
    queryKey: ["record", id, "stored"],
    queryFn: ({ signal }) => getRecord(api, id, false, signal),
    ...keep,
  });
  return { outcome: query.data ?? null, refetch: () => void query.refetch() };
}

export function useReplay(
  id: string,
  enabled: boolean,
): { outcome: RecordOutcome | null; fetching: boolean; refetch: () => void } {
  const api = useApi();
  const query = useQuery({
    queryKey: ["record", id],
    queryFn: ({ signal }) => getRecord(api, id, true, signal),
    enabled,
    ...keep,
  });
  return { outcome: query.data ?? null, fetching: query.isFetching, refetch: () => void query.refetch() };
}

/**
 * `/parse` of the record's `canonical` (its default and limit clauses) and of its `identification_query` (is
 * it all-negative?), as the methods text reads them. `settled` is false until both have answered (or failed),
 * so the text doesn't change under the reader; a failed parse is `null` and the text says less, never guesses.
 */
export function useRecordParses(record: SearchRecord | null): {
  canonical: ParseResponse | null;
  identification: ParseResponse | null;
  settled: boolean;
} {
  const api = useApi();
  const canonical = useQuery({
    ...parseQuery(api, record?.canonical ?? "", "native"),
    enabled: record !== null,
  });
  const idq = record?.identification_query ?? "";
  const identification = useQuery({
    ...parseQuery(api, idq, "native"),
    enabled: record !== null && idq !== "",
  });
  const parsed = (d: typeof canonical.data) => (d?.kind === "parsed" ? d.result : null);
  return {
    canonical: parsed(canonical.data),
    identification: parsed(identification.data),
    settled:
      record !== null && canonical.data !== undefined && (idq === "" || identification.data !== undefined),
  };
}
