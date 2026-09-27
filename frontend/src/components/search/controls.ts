"use client";

/**
 * How a filter control decides whether it may act (design W13; spec 05 "controls are disabled with the
 * reason, not refused after the click"). Every click is a reducer action on the searched `q`; `blockOf` is
 * `whyBlocked` plus the one component-level refusal, `DRAFT_DIRTY` (the editor has unsearched edits, which a
 * click would discard), and the case where `/parse` hasn't answered for any query yet.
 */
import { useEffect, useState } from "react";
import type { CodePointSpan } from "@/api/spans";
import type { ParseOutcome } from "@/editor/parse";
import {
  EVERY_YEAR,
  whyBlocked,
  type Mode,
  type ParsedFilters,
  type QueryLimits,
  type SearchAction,
  type SearchState,
  type SearchStateErrorCode,
} from "@/lib/search-state";
import { DRAFT_DIRTY_MESSAGE } from "./search-workspace";

/** `/parse`'s report for a searched query: what the sidebar and banner read their clauses from. */
export interface ParseView {
  /** The `(q, mode)` it was parsed from (the reducer refuses it as stale for any other). */
  readonly q: string;
  readonly mode: Mode;
  /** `null` when the query has errors (SB-5). */
  readonly filters: ParsedFilters | null;
  readonly defaults: readonly string[];
}

export type BlockCode = SearchStateErrorCode | "DRAFT_DIRTY" | "NO_FILTERS";

export interface Block {
  readonly code: BlockCode;
  readonly message: string;
}

export const NO_FILTERS_MESSAGE = "Filters are unavailable until the query parses.";

/** Refusals about one value (its own note), not about the field (the field's note). */
export const VALUE_CODES: readonly BlockCode[] = [
  "LAST_VALUE",
  "ALREADY_INCLUDED",
  "NOT_INCLUDED",
  "BAD_VALUE",
];

/** What a control needs to act: the search, the report, the draft, the limits, and how to act. */
export interface Controls {
  readonly state: SearchState;
  readonly parse: ParseView | null;
  readonly dirty: boolean;
  readonly limits: QueryLimits;
  /** Apply `action` (already checked with `blockOf`) and announce `said` once its search lands. */
  readonly act: (action: SearchAction, said: string) => void;
  /** Select a code-point span of the searched `q` in the editor (only while the draft is `q`). */
  readonly selectInQuery: (span: CodePointSpan) => void;
  /** Put `text` in the editor as a draft and select `[from, to)` of it (code points). */
  readonly draftAndSelect: (text: string, span: CodePointSpan) => void;
}

export function blockOf(c: Controls, action: SearchAction): Block | null {
  if (c.dirty) return { code: "DRAFT_DIRTY", message: DRAFT_DIRTY_MESSAGE };
  if (c.parse === null) return staleOf(c.state, action, c.limits);
  if (c.parse.q === c.state.q && c.parse.mode === c.state.mode && c.parse.filters === null) {
    return { code: "NO_FILTERS", message: NO_FILTERS_MESSAGE };
  }
  const e = whyBlocked(c.state, action, c.limits);
  return e === null ? null : { code: e.code, message: e.message };
}

/**
 * `/parse` hasn't answered for any query yet: the reducer's own STALE_CLAUSE refusal, asked with a clause
 * read from no query (so its wording stays the reducer's, in one place).
 */
function staleOf(state: SearchState, action: SearchAction, limits: QueryLimits): Block | null {
  const from = { negated: false, source: `${state.q} `, mode: state.mode, span: [0, 0] } as const;
  let probe: SearchAction;
  switch (action.type) {
    case "facetToggle":
    case "includeExcluded":
      probe = { ...action, clause: { ...from, field: action.field, values: [action.value] } };
      break;
    case "yearSet":
    case "yearClear":
    case "yearAdd":
    case "yearRemove":
      probe = { ...action, clause: { ...from, field: "year", ranges: [EVERY_YEAR] } };
      break;
    default:
      return null;
  }
  const e = whyBlocked(state, probe, limits);
  return e === null ? null : { code: e.code, message: e.message };
}

/**
 * For STALE_CLAUSE the note stays empty for its first 500 ms (design W13: `/parse` usually answers first, so
 * the reason would only flash); the control is `aria-disabled` throughout.
 */
export const STALE_QUIET_MS = 500;

export function useShowStale(stale: boolean): boolean {
  return useAfter(stale, STALE_QUIET_MS);
}

/** `flag`, once it has been true for `ms` (a quiet start: "Searching…" after 300 ms, W4). */
export function useAfter(flag: boolean, ms: number): boolean {
  const [shown, setShown] = useState(false);
  useEffect(() => {
    if (!flag) return;
    const t = setTimeout(() => setShown(true), ms);
    return () => {
      clearTimeout(t);
      setShown(false);
    };
  }, [flag, ms]);
  return flag && shown;
}

/** A span the client read back as `number[]` (nextjs-conventions: `openapi-fetch` widens tuples), checked. */
function pairOf(span: readonly number[]): [number, number] {
  const [start, end] = span;
  if (span.length !== 2 || start === undefined || end === undefined || !(0 <= start && start <= end)) {
    throw new RangeError(`not a span: [${span.join(", ")}]`);
  }
  return [start, end];
}

type Spanned = { span: readonly number[] | null; blocking_spans: readonly (readonly number[])[] };

const spansOf = (c: Spanned) => ({
  span: c.span === null ? null : pairOf(c.span),
  blocking_spans: c.blocking_spans.map(pairOf),
});

/**
 * `/parse`'s answer for a searched query as the sidebar reads it: `filters` with every span checked, or `null`
 * when the query has errors (or, a server bug, a span isn't one: then no click is offered at all).
 */
export function parseViewOf(outcome: ParseOutcome | null): ParseView | null {
  if (outcome === null || outcome.kind !== "parsed") return null;
  const { result } = outcome;
  let filters: ParsedFilters | null = null;
  if (result.errors.length === 0 && result.filters !== null) {
    try {
      const f = result.filters;
      filters = {
        venue: { ...f.venue, ...spansOf(f.venue) },
        track: { ...f.track, ...spansOf(f.track) },
        status: { ...f.status, ...spansOf(f.status) },
        year: { ...f.year, ...spansOf(f.year) },
      };
    } catch (e) {
      console.error("openproceedings: /parse sent a filter span that isn't one", e);
      filters = null;
    }
  }
  return { q: outcome.q, mode: outcome.mode, filters, defaults: result.defaults };
}
