"use client";

/**
 * `/paper/[id]` (spec 05 §Pages; design P1–P5; copy PA-1–7): the full record, with the query in the link
 * (`?q=&mode=`) drawn as `GET /papers/{id}?q=&mode=` returns it: `matched` and `highlights`, the API's spans
 * only (never re-matched). Without `q` (a direct link) the record alone. A `q` the API refuses (422, 429, 503
 * `API_BUSY`) is dropped: the paper is fetched without it and a one-line notice says why. 404 and 422
 * `API_BAD_PARAM` (a malformed id) are the not-found state.
 */
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import type { MethodResponse } from "openapi-fetch";
import type { Api } from "@/api/client";
import { useMeta } from "@/api/hooks";
import { outcomeOf, type Failure } from "@/api/outcome";
import { useApi } from "@/components/providers";
import { utf16Spans } from "@/lib/excerpt";
import { INITIAL_STATE, searchHref, type Mode } from "@/lib/search-state";
import { CopyButton } from "../copy-button";
import { Highlighted } from "../highlighted";
import { PaperBadges, statusWords } from "../paper-badges";
import { PaperLinks } from "../paper-links";
import { ABSTRACT_WITHHELD, WITHHELD_TERMS } from "../search/hit-item";
import { FailureBlock } from "../search/search-states";

export type PaperResponse = MethodResponse<Api, "get", "/api/v1/papers/{id}">;

export type PaperOutcome =
  | {
      readonly kind: "ok";
      readonly data: PaperResponse;
      /** The link's `q` was refused, so this is the paper without it (P4). */
      readonly dropped: { readonly status: number; readonly code: string } | null;
    }
  | { readonly kind: "not_found" }
  | Failure;

/** The refusals of a `q` that still let the paper be shown without it (P4). */
function dropsQuery(f: Failure): boolean {
  if (f.kind !== "refused") return false;
  if (f.status === 422) return f.error.code !== "API_BAD_PARAM";
  return f.status === 429 || f.error.code === "API_BUSY";
}

function notFound(f: Failure): boolean {
  return f.kind === "refused" && (f.status === 404 || (f.status === 422 && f.error.code === "API_BAD_PARAM"));
}

export async function getPaper(
  api: Api,
  id: string,
  q: string | null,
  mode: Mode,
  signal?: AbortSignal,
): Promise<PaperOutcome> {
  const fetchPaper = (withQuery: boolean) =>
    outcomeOf(
      () =>
        api.GET("/api/v1/papers/{id}", {
          // `mode` only with `q`: `scholar` without `q` is 422 API_BAD_PARAM
          params: { path: { id }, query: withQuery && q !== null ? { q, mode } : {} },
          ...(signal === undefined ? {} : { signal }),
        }),
      signal,
    );
  const first = await fetchPaper(q !== null);
  if (first.kind === "ok") return { kind: "ok", data: first.data, dropped: null };
  if (notFound(first)) return { kind: "not_found" };
  if (q === null || !dropsQuery(first) || first.kind !== "refused") return first;
  const bare = await fetchPaper(false);
  if (bare.kind === "ok") {
    return { kind: "ok", data: bare.data, dropped: { status: first.status, code: first.error.code } };
  }
  return notFound(bare) ? { kind: "not_found" } : bare;
}

/** A mode in words, wherever one is shown (PA-2, as RC-8). */
export function modeWords(mode: Mode): string {
  return mode === "scholar" ? "Google Scholar syntax" : "native syntax";
}

/** `2026-09-18T10:02:33Z` → `2026-09-18 10:02 UTC` (the provenance table's Fetched column). */
export function fetchedText(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return `${d.toISOString().slice(0, 10)} ${d.toISOString().slice(11, 16)} UTC`;
}

function claimValue(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (Array.isArray(v)) return v.join("; ");
  return String(v);
}

const h2 = "text-base font-semibold";

function Provenance({ claims }: { claims: PaperResponse["paper"]["provenance"] }) {
  if (claims.length === 0) return <p className="text-sm text-muted-foreground">No provenance recorded.</p>;
  const evidence = (c: (typeof claims)[number]) => (
    <>
      {c.evidence ?? ""}
      {c.url !== null && (
        <>
          {c.evidence !== null && " "}
          <a href={c.url} rel="noopener noreferrer" className="underline underline-offset-4">
            source <span aria-hidden="true">▸</span>
          </a>
        </>
      )}
    </>
  );
  return (
    <>
      <table className="hidden w-full text-left text-sm md:table">
        <thead>
          <tr className="border-b">
            <th scope="col" className="py-1 pr-3">
              Field
            </th>
            <th scope="col" className="py-1 pr-3">
              Value
            </th>
            <th scope="col" className="py-1 pr-3">
              Source
            </th>
            <th scope="col" className="py-1 pr-3">
              Fetched
            </th>
            <th scope="col" className="py-1">
              Evidence
            </th>
          </tr>
        </thead>
        <tbody>
          {claims.map((c, i) => (
            <tr key={i} className="border-b align-top">
              <th scope="row" className="py-1 pr-3 font-mono font-normal">
                {c.field}
              </th>
              <td className="max-w-md py-1 pr-3 break-words">{claimValue(c.value)}</td>
              <td className="py-1 pr-3 font-mono">{c.source}</td>
              <td className="py-1 pr-3 whitespace-nowrap tabular-nums">{fetchedText(c.fetched_at)}</td>
              <td className="py-1 break-words">{evidence(c)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="space-y-2 md:hidden">
        {claims.map((c, i) => (
          <dl key={i} className="grid grid-cols-[6rem_minmax(0,1fr)] gap-x-2 border-b pb-2 text-sm">
            <dt>Field</dt>
            <dd className="font-mono">{c.field}</dd>
            <dt>Value</dt>
            <dd className="break-words">{claimValue(c.value)}</dd>
            <dt>Source</dt>
            <dd className="font-mono">{c.source}</dd>
            <dt>Fetched</dt>
            <dd className="tabular-nums">{fetchedText(c.fetched_at)}</dd>
            <dt>Evidence</dt>
            <dd className="break-words">{evidence(c)}</dd>
          </dl>
        ))}
      </div>
    </>
  );
}

function Paper({
  data,
  q,
  mode,
  dropped,
}: {
  data: PaperResponse;
  q: string | null;
  mode: Mode;
  dropped: { status: number; code: string } | null;
}) {
  const { paper } = data;
  const lit = data.highlights;
  const title = lit === null ? [] : (utf16Spans(paper.title, lit.title) ?? []);
  const abstract =
    lit === null || paper.abstract === null ? [] : (utf16Spans(paper.abstract, lit.abstract) ?? []);
  return (
    <article className="space-y-4">
      <h1 className="text-xl font-semibold break-words">
        <Highlighted text={paper.title} spans={title} />
      </h1>
      <PaperBadges
        venue={paper.venue}
        year={paper.year}
        track={paper.track}
        presentation={paper.presentation}
        status={paper.status}
      />
      {paper.authors.length > 0 && <p className="text-sm">{paper.authors.join(", ")}</p>}
      {paper.status !== "accepted" && (
        <p className="text-sm">
          Status: {statusWords(paper.status)} — submitted to {paper.venue_name},{" "}
          {paper.status === "unknown" ? "not known to be in its proceedings" : "not in its proceedings"}.
        </p>
      )}
      {q !== null && dropped !== null && (
        <p role="status" className="text-sm">
          <span aria-hidden="true">ⓘ </span>
          {dropped.status === 429 ? (
            "The query in this link couldn't be run just now (too many requests), so the paper is shown without highlights."
          ) : (
            <>
              The query in this link couldn&apos;t be run (<code className="font-mono">{dropped.code}</code>),
              so the paper is shown without highlights.
            </>
          )}
        </p>
      )}
      {q !== null && dropped === null && data.matched === true && (
        <p className="text-sm break-words">
          <span aria-hidden="true">✔ </span>Matches <code className="font-mono break-all">{q}</code> (
          {modeWords(mode)}): matched terms are highlighted.
          {data.abstract_withheld && ` ${WITHHELD_TERMS}`}
        </p>
      )}
      {q !== null && dropped === null && data.matched === false && (
        <p className="text-sm break-words">
          <span aria-hidden="true">✖ </span>Doesn&apos;t match{" "}
          <code className="font-mono break-all">{q}</code> ({modeWords(mode)}). Nothing is highlighted. A
          filter may remove it (for example the default track or status filter), or it lacks a term the query
          requires.
        </p>
      )}
      <section aria-labelledby="abstract-h" className="space-y-1">
        <h2 id="abstract-h" className={h2}>
          Abstract
        </h2>
        {data.abstract_withheld ? (
          <p className="text-sm text-muted-foreground">{ABSTRACT_WITHHELD}</p>
        ) : paper.abstract === null ? (
          <p className="text-sm text-muted-foreground">No abstract in the index</p>
        ) : (
          <p className="text-sm break-words">
            <Highlighted text={paper.abstract} spans={abstract} />
          </p>
        )}
      </section>
      <section aria-labelledby="links-h" className="space-y-1">
        <h2 id="links-h" className={h2}>
          Links
        </h2>
        <PaperLinks urls={paper.urls} label="Links" />
      </section>
      <section aria-labelledby="ids-h" className="space-y-1 text-sm">
        <h2 id="ids-h" className={h2}>
          Identifiers
        </h2>
        <p className="flex flex-wrap items-center gap-x-2">
          <code className="font-mono break-all">{paper.id}</code>
          <CopyButton text={paper.id} label="Copy paper id" />
        </p>
        {paper.venue_id_raw !== null && (
          <p>
            venue id <code className="font-mono break-all">{paper.venue_id_raw}</code>
          </p>
        )}
        <p>
          content hash <code className="font-mono break-all">{paper.content_hash}</code>
        </p>
      </section>
      <section aria-labelledby="prov-h" className="space-y-1">
        <h2 id="prov-h" className={h2}>
          Where each field came from
        </h2>
        <Provenance claims={paper.provenance} />
      </section>
      <p className="text-xs text-muted-foreground">
        Index <code className="font-mono break-all">{data.index_version}</code> · tokenizer{" "}
        {data.tokenizer_version} · query version {data.query_version}
      </p>
    </article>
  );
}

export function PaperView({ id, q, mode }: { id: string; q: string | null; mode: Mode }) {
  const api = useApi();
  const meta = useMeta();
  const query = useQuery({
    queryKey: ["paper", id, q, mode] as const,
    queryFn: ({ signal }) => getPaper(api, id, q, mode, signal),
  });
  const back = q === null ? "/search" : searchHref({ ...INITIAL_STATE, q, mode });
  const outcome = query.data ?? null;
  return (
    <section className="mx-auto max-w-3xl space-y-4">
      <p className="text-sm">
        <Link href={back} className="underline underline-offset-4">
          <span aria-hidden="true">◂ </span>Back to results
        </Link>
      </p>
      {outcome === null && (
        <p role="status" className="text-sm text-muted-foreground">
          Loading the paper…
        </p>
      )}
      {outcome?.kind === "ok" && <Paper data={outcome.data} q={q} mode={mode} dropped={outcome.dropped} />}
      {outcome?.kind === "not_found" && (
        <div className="space-y-2">
          <h1 className="text-xl font-semibold">Paper not found</h1>
          <p className="text-sm">
            No paper with that id
            {meta !== null && (
              <>
                {" "}
                in index <code className="font-mono break-all">{meta.index_version}</code>
              </>
            )}
            . The link may be mistyped, or the paper isn&apos;t in the index this instance serves.
          </p>
          <p className="text-sm">
            <Link href="/search" className="underline underline-offset-4">
              Search
            </Link>
          </p>
        </div>
      )}
      {outcome !== null && outcome.kind !== "ok" && outcome.kind !== "not_found" && (
        <>
          <h1 className="sr-only">Paper</h1>
          <FailureBlock failure={outcome} onRetry={() => void query.refetch()} focus={false} />
        </>
      )}
    </section>
  );
}
