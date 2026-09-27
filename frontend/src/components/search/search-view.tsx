"use client";

/**
 * The whole `/search` workspace (spec 05 §`/search` layout; design W4–W14): the query half
 * (`SearchWorkspace`, TASK-041/043) and the results half drawn in its `results` slot: the index-swap notice,
 * the failure and stale states, expansions, the results header, exclusion banner and Limits line, the filter
 * sidebar, sort, hits and paging.
 *
 * `GET /search` runs here. A 422 for the searched query goes back up as the workspace's `refusal`, which draws
 * its diagnostics on the editor (W6, W7). The last answer that succeeded stays on screen, marked stale, while
 * a newer search is in flight or has failed. Every control is a reducer action: filters and sort push the
 * URL, paging replaces it (design §What changes the URL).
 */
import { useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";
import { useMeta } from "@/api/hooks";
import { codePointSpanToUtf16, type CodePointSpan } from "@/api/spans";
import { plural } from "@/editor/diagnostics";
import { useSearchedParse } from "@/editor/use-parse";
import {
  DEFAULT_LIMITS,
  PAGE_SIZE,
  reduce,
  searchHref,
  SearchStateError,
  SORTS,
  whyBlocked,
  type SearchAction,
  type SearchState,
  type Sort,
} from "@/lib/search-state";
import { CopyButton } from "../copy-button";
import { parseViewOf, useAfter, type Controls, type ParseView } from "./controls";
import { ExclusionBanner } from "./exclusion-banner";
import { limitsOf, type Limit } from "./exclusions";
import { ExpansionsRow } from "./expansions-row";
import { FilterSidebar } from "./filter-sidebar";
import { HitItem } from "./hit-item";
import { FailureBlock, IndexSwapNotice, StaleNotice } from "./search-states";
import { SearchWorkspace, type SearchRefusal } from "./search-workspace";
import { useWorkspaceSlot } from "./workspace-slot";
import { sameSearch, useSearch, type SearchOutcome, type SearchResponse } from "./use-search";

type Good = SearchOutcome & { readonly kind: "ok" };

export const SORT_LABELS: Record<Sort, string> = {
  relevance: "Relevance",
  year_desc: "Year, newest first",
  year_asc: "Year, oldest first",
  title: "Title",
};

/** "Searching…" appears only after this long, so a fast answer doesn't flash it (W4). */
export const SEARCHING_QUIET_MS = 300;

/** `⌈total / PAGE_SIZE⌉`: how many pages a search has. */
export function pageCount(total: number): number {
  return Math.ceil(total / PAGE_SIZE);
}

export function SearchView({ state }: { state: SearchState }) {
  const search = useSearch(state);
  const { outcome } = search;

  // The last answer that succeeded, kept on screen (marked stale) while a newer one is in flight or failed;
  // and the index-swap notice when an answer for the same (q, mode) came from another index (W12).
  const [good, setGood] = useState<Good | null>(null);
  const [swap, setSwap] = useState<{ from: string; to: string } | null>(null);
  if (outcome?.kind === "ok" && outcome !== good) {
    if (
      good !== null &&
      good.state.q === outcome.state.q &&
      good.state.mode === outcome.state.mode &&
      good.data.index_version !== outcome.data.index_version
    ) {
      setSwap({ from: good.data.index_version, to: outcome.data.index_version });
    }
    setGood(outcome);
  }

  const current = outcome !== null && sameSearch(outcome.state, state) ? outcome : null;
  const refusal: SearchRefusal | null =
    current?.kind === "refused" && current.status === 422
      ? { q: state.q, mode: state.mode, error: current.error }
      : null;
  const zero = current?.kind === "ok" && current.data.total === 0;

  return (
    <SearchWorkspace
      state={state}
      refusal={refusal}
      openTree={zero}
      results={
        state.q.trim() === "" ? null : (
          <Results
            state={state}
            current={current}
            good={good}
            fetching={search.fetching}
            refetch={search.refetch}
            swap={swap}
            onDismissSwap={() => setSwap(null)}
          />
        )
      }
    />
  );
}

interface ResultsProps {
  readonly state: SearchState;
  /** The answer for exactly `state`, or `null` while it is in flight. */
  readonly current: SearchOutcome | null;
  readonly good: Good | null;
  readonly fetching: boolean;
  readonly refetch: () => void;
  readonly swap: { from: string; to: string } | null;
  readonly onDismissSwap: () => void;
}

function Results({ state, current, good, fetching, refetch, swap, onDismissSwap }: ResultsProps) {
  const router = useRouter();
  const slot = useWorkspaceSlot();
  const meta = useMeta();
  const limits = meta?.limits ?? DEFAULT_LIMITS;
  const searched = useSearchedParse(state.q, state.mode);

  // The last /parse report for a searched query. While /parse catches up with a new q, the previous report
  // stays: its clauses are then stale, so the reducer refuses them (STALE_CLAUSE) and the controls say so.
  const [report, setReport] = useState<ParseView | null>(null);
  const fresh = parseViewOf(searched);
  if (fresh !== null && (report === null || report.q !== fresh.q || report.mode !== fresh.mode)) {
    setReport(fresh);
  }
  const parse = fresh ?? report;

  // Announcements (RH-1): what a click did, then the new total, once the answer for it lands.
  const said = useRef<{ state: SearchState; text: string } | null>(null);
  const [announcement, setAnnouncement] = useState("");
  useEffect(() => {
    if (good === null) return;
    const total = `${plural(good.data.total, "paper")}.`;
    const pending = said.current;
    if (pending !== null && sameSearch(pending.state, good.state)) {
      said.current = null;
      setAnnouncement(`${pending.text} ${total}`);
    } else {
      setAnnouncement(total);
    }
  }, [good]);

  const heading = useRef<HTMLHeadingElement>(null);
  const count = useRef<HTMLElement>(null);
  const focusHeading = useRef(false);
  useEffect(() => {
    if (focusHeading.current) {
      focusHeading.current = false;
      heading.current?.focus();
    }
  }, [state.page]);

  // A failure's heading takes focus only after a search the reader started, not on load (W6–W10).
  const [firstKey] = useState(() => `${state.q}\u0000${state.mode}\u0000${state.sort}\u0000${state.page}`);
  const readerStarted = firstKey !== `${state.q}\u0000${state.mode}\u0000${state.sort}\u0000${state.page}`;

  const go = (action: SearchAction, text: string, how: "push" | "replace" = "push") => {
    let next: SearchState;
    try {
      next = reduce(state, action, limits);
    } catch (e) {
      // Controls check whyBlocked before acting, so this is a bug: say so rather than do nothing silently.
      if (e instanceof SearchStateError) {
        console.error("openproceedings: a control acted although the reducer refuses it", e);
        setAnnouncement(e.message);
        return;
      }
      throw e;
    }
    said.current = { state: next, text };
    if (how === "push") router.push(searchHref(next));
    else router.replace(searchHref(next));
  };

  const controls: Controls = {
    state,
    parse,
    dirty: slot.dirty,
    limits,
    act: go,
    selectInQuery: (span: CodePointSpan) => {
      try {
        const [a, b] = codePointSpanToUtf16(state.q, span);
        slot.select(a, b);
      } catch (e) {
        console.error("openproceedings: a clause span doesn't fit the query", e);
      }
    },
    draftAndSelect: (text: string, span: CodePointSpan) => {
      const [a, b] = codePointSpanToUtf16(text, span);
      slot.draftAndSelect(text, a, b);
    },
  };

  const failure = current !== null && current.kind !== "ok" ? current : null;
  const shown = good;
  const shownIsCurrent = shown !== null && current === shown;
  const searching = useAfter(current === null && fetching, SEARCHING_QUIET_MS);
  const sidebarId = useId();
  const [filtersOpen, setFiltersOpen] = useState(false);

  const is422 = failure?.kind === "refused" && failure.status === 422;
  const errorCount =
    is422 && failure.kind === "refused" ? Math.max(failure.error.diagnostics?.length ?? 0, 1) : 0;
  const staleShown = shown !== null && failure !== null;
  const restore =
    shown !== null && (shown.state.q !== state.q || shown.state.mode !== state.mode)
      ? () => router.push(searchHref({ ...shown.state, sort: state.sort, page: 1 }))
      : null;

  return (
    <div className="space-y-3">
      {swap !== null && <IndexSwapNotice from={swap.from} to={swap.to} onDismiss={onDismissSwap} />}
      {failure !== null && !is422 && (
        <FailureBlock failure={failure} onRetry={refetch} focus={readerStarted} />
      )}
      {is422 && shown === null && (
        <p role="alert" className="text-sm">
          No results: the query has {plural(errorCount, "error")}. Fix it above and search again.
        </p>
      )}
      {staleShown && <StaleNotice q={shown.state.q} total={shown.data.total} onRestore={restore} />}
      {shown === null && failure === null && (
        <p role="status" className="min-h-5 text-sm text-muted-foreground">
          {searching ? "Searching…" : ""}
        </p>
      )}
      {shown !== null && (
        <ResultsBody
          state={state}
          response={shown.data}
          shownState={shown.state}
          controls={controls}
          vocabulary={meta?.values ?? {}}
          dim={staleShown || !shownIsCurrent}
          busy={current === null && fetching}
          searching={searching}
          announcement={announcement}
          heading={heading}
          count={count}
          sidebarId={sidebarId}
          filtersOpen={filtersOpen}
          onToggleFilters={() => setFiltersOpen(!filtersOpen)}
          onSort={(sort) => go({ type: "sort", sort }, `Sorted by ${SORT_LABELS[sort].toLowerCase()}.`)}
          onPage={(page) => {
            focusHeading.current = true;
            go({ type: "page", page }, `Page ${page}.`, "replace");
          }}
          onIncluded={() => count.current?.focus()}
        />
      )}
    </div>
  );
}

interface BodyProps {
  readonly state: SearchState;
  readonly response: SearchResponse;
  /** The search `response` answers (the URL's while it is current; the last good one otherwise). */
  readonly shownState: SearchState;
  readonly controls: Controls;
  readonly vocabulary: Readonly<Partial<Record<string, readonly string[]>>>;
  readonly dim: boolean;
  readonly busy: boolean;
  readonly searching: boolean;
  readonly announcement: string;
  readonly heading: React.RefObject<HTMLHeadingElement | null>;
  readonly count: React.RefObject<HTMLElement | null>;
  readonly sidebarId: string;
  readonly filtersOpen: boolean;
  readonly onToggleFilters: () => void;
  readonly onSort: (sort: Sort) => void;
  readonly onPage: (page: number) => void;
  readonly onIncluded: () => void;
}

function ResultsBody({
  state,
  response,
  shownState,
  controls,
  vocabulary,
  dim,
  busy,
  searching,
  announcement,
  heading,
  count,
  sidebarId,
  filtersOpen,
  onToggleFilters,
  onSort,
  onPage,
  onIncluded,
}: BodyProps) {
  const { parse } = controls;
  const current = parse !== null && parse.q === shownState.q && parse.mode === shownState.mode;
  const written: Limit[] =
    current && parse.filters !== null
      ? limitsOf(shownState.q, parse.filters, parse.defaults, response.facets, vocabulary)
      : [];
  const total = response.total;
  const pages = pageCount(total);
  const zero = total === 0;
  return (
    <div className={dim ? "opacity-60" : undefined}>
      <ExpansionsRow expansions={response.query.expansions} />
      <div className="mt-3 gap-x-6 md:grid md:grid-cols-[15rem_minmax(0,1fr)] md:grid-rows-[auto_1fr]">
        <div className="min-w-0 space-y-2 md:col-start-2 md:row-start-1">
          <p className="flex flex-wrap items-center gap-x-2 text-sm">
            <strong ref={count} tabIndex={-1} className="tabular-nums">
              {zero ? "0 papers match" : plural(total, "paper")}
            </strong>
            <span aria-hidden="true">·</span>
            <span>
              index <code className="font-mono break-all">{response.index_version}</code>
            </span>
            <CopyButton text={response.index_version} label="Copy index version" />
            {searching && <span className="text-muted-foreground">Searching…</span>}
          </p>
          <p role="status" aria-live="polite" className="sr-only">
            {announcement}
          </p>
          <ExclusionBanner response={response} controls={controls} onIncluded={onIncluded} />
          <LimitsLine limits={written} known={current && parse.filters !== null} />
          {zero && <ZeroResults canonical={response.query.canonical} excluded={response.excluded.total} />}
          <button
            type="button"
            aria-expanded={filtersOpen}
            aria-controls={sidebarId}
            onClick={onToggleFilters}
            className="min-h-8 rounded-md border px-3 text-sm hover:bg-muted md:hidden"
          >
            Filters ({written.length} active)
          </button>
        </div>
        <div className="mt-3 min-w-0 md:col-start-1 md:row-span-2 md:row-start-1 md:mt-0">
          <FilterSidebar
            id={sidebarId}
            controls={controls}
            facets={response.facets}
            vocabulary={vocabulary}
            hiddenWhenNarrow={!filtersOpen}
          />
        </div>
        <div className="mt-3 min-w-0 space-y-2 md:col-start-2 md:row-start-2">
          <label className="flex items-center gap-2 text-sm">
            Sort
            <select
              value={state.sort}
              onChange={(e) => {
                const sort = SORTS.find((s) => s === e.target.value);
                if (sort !== undefined) onSort(sort);
              }}
              className="min-h-8 rounded-md border border-input bg-background px-2"
            >
              {SORTS.map((s) => (
                <option key={s} value={s}>
                  {SORT_LABELS[s]}
                </option>
              ))}
            </select>
          </label>
          {!zero && (
            <h2 ref={heading} tabIndex={-1} className="text-sm font-semibold">
              Results, page {shownState.page.toLocaleString("en-US")} of {pages.toLocaleString("en-US")}
            </h2>
          )}
          {!zero && response.hits.length === 0 && (
            <p className="text-sm">
              No papers on page {shownState.page.toLocaleString("en-US")} — this search has{" "}
              {plural(pages, "page")}.{" "}
              <button type="button" onClick={() => onPage(pages)} className="underline underline-offset-4">
                Go to the last page
              </button>
            </p>
          )}
          <ol aria-busy={busy} aria-label="Results">
            {response.hits.map((hit) => (
              <li key={hit.id}>
                <HitItem hit={hit} q={shownState.q} mode={shownState.mode} />
              </li>
            ))}
          </ol>
          {pages > 1 && <Paging page={state.page} pages={pages} onPage={onPage} state={state} />}
        </div>
      </div>
    </div>
  );
}

function LimitsLine({ limits, known }: { limits: readonly Limit[]; known: boolean }) {
  if (!known) return null;
  return (
    <div className="text-sm">
      <span className="font-semibold">Limits you wrote:</span>{" "}
      {limits.length === 0 ? (
        "none"
      ) : (
        <ul className="inline">
          {limits.map((l, i) => (
            <li key={l.field} className="inline break-words">
              {i > 0 && "; "}
              {l.text === null ? (
                <>
                  <code className="font-mono">{l.field}:</code> (several clauses — see the query)
                </>
              ) : (
                <code className="font-mono break-all">{l.text}</code>
              )}
              {l.leavesOut.length > 0 &&
                ` — leaves out ${l.leavesOut.map(([v, n]) => `${n.toLocaleString("en-US")} ${v}`).join(" · ")}`}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** W8 (ER-9, pre-pass S6): what matched nothing, what was excluded, and why exact words may be the reason. */
function ZeroResults({ canonical, excluded }: { canonical: string; excluded: number }) {
  return (
    <div className="space-y-1 text-sm">
      <p className="break-words">
        0 papers match <code className="font-mono break-all">{canonical}</code>.
        {excluded > 0 && ` ${excluded.toLocaleString("en-US")} were excluded by the default filters above.`}
      </p>
      <p>
        Check the limits, the expansions and how the query was read. Words match exactly:{" "}
        <code className="font-mono">benchmarks</code> doesn&apos;t find{" "}
        <code className="font-mono">benchmark</code>; <code className="font-mono">benchmark$</code> finds
        both.
      </p>
    </div>
  );
}

/** Numbered pages (design W5 "Paging"): ◂ Previous · Page n of m · Next ▸, and a Go to page input. */
function Paging({
  page,
  pages,
  onPage,
  state,
}: {
  page: number;
  pages: number;
  onPage: (page: number) => void;
  state: SearchState;
}) {
  const [typed, setTyped] = useState("");
  const [error, setError] = useState("");
  const inputId = useId();
  const errorId = useId();
  const nav = "min-h-8 rounded-md border px-3 hover:bg-muted";
  return (
    <nav aria-label="Pages" className="flex flex-wrap items-center gap-3 pt-2 text-sm">
      <button
        type="button"
        aria-disabled={page <= 1 ? true : undefined}
        onClick={() => page > 1 && onPage(page - 1)}
        className={`${nav} ${page <= 1 ? "opacity-60" : ""}`}
      >
        <span aria-hidden="true">◂ </span>Previous
      </button>
      <span className="tabular-nums">
        Page {page.toLocaleString("en-US")} of {pages.toLocaleString("en-US")}
      </span>
      <button
        type="button"
        aria-disabled={page >= pages ? true : undefined}
        onClick={() => page < pages && onPage(page + 1)}
        className={`${nav} ${page >= pages ? "opacity-60" : ""}`}
      >
        Next<span aria-hidden="true"> ▸</span>
      </button>
      <form
        className="flex items-center gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          const n = /^[0-9]+$/.test(typed.trim()) ? Number(typed.trim()) : Number.NaN;
          const refused = whyBlocked(state, { type: "page", page: Number.isNaN(n) ? 0 : n });
          if (refused !== null) {
            setError(refused.message.replace(/^0 is/, `${JSON.stringify(typed)} is`));
          } else if (n > pages) {
            setError(
              `Page ${n.toLocaleString("en-US")} is past the last page — this search has ${plural(pages, "page")}. ` +
                `Choose a page from 1 to ${pages.toLocaleString("en-US")}.`,
            );
          } else {
            setError("");
            onPage(n);
          }
        }}
      >
        <label htmlFor={inputId}>Go to page</label>
        <input
          id={inputId}
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
          inputMode="numeric"
          size={5}
          aria-invalid={error !== "" ? true : undefined}
          aria-describedby={errorId}
          className="min-h-8 rounded-md border border-input bg-background px-2 tabular-nums"
        />
        <button type="submit" className={nav}>
          Go
        </button>
      </form>
      <p id={errorId} role="status" aria-live="polite" className="w-full text-sm empty:hidden">
        {error}
      </p>
    </nav>
  );
}
