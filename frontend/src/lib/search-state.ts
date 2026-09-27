/**
 * The URL↔state reducer for /search (spec 05 §URL is state; guarantee 3; nextjs-conventions skill).
 *
 * `SearchState` is the whole search, and it is exactly the URL: `/search?q=&mode=&sort=&page=`.
 * - **`q` is the only result-set state.** Every filter lives in it. A facet click, an "include" button
 *   or a builder edit produces a new `q` string; nothing stores a filter anywhere else. `mode` says how
 *   `q` is read (native or Scholar syntax), so it is part of the search too (`resultSetKey`).
 * - `sort` and `page` are view state: they order and window the same set, never change it. The API's
 *   `offset`/`limit` are derived from `page` (`toSearchRequest`).
 *
 * The client never parses `q`. A filter rewrite takes the clause's code-point span and values from the
 * server's `/parse` result (`FilterClause`) and splices a new clause in; the server then re-parses.
 * Every function here is pure.
 */
import { codePointLength, codePointSpanToUtf16, type CodePointSpan } from "@/api/spans";

export const MODES = ["native", "scholar"] as const;
export type Mode = (typeof MODES)[number];

/** Spec 03 §Ranking. `semantic` joins when spec 06 is enabled. */
export const SORTS = ["relevance", "year_desc", "year_asc", "title"] as const;
export type Sort = (typeof SORTS)[number];

/** Results per page; the API's `limit` (spec 03 default 50, spec 04 max 200). */
export const PAGE_SIZE = 50;

/** Highest page the URL may name: offsets stay under 500,000, several times the whole corpus. */
export const MAX_PAGE = 10_000;

export interface SearchState {
  readonly q: string;
  readonly mode: Mode;
  readonly sort: Sort;
  readonly page: number;
}

export const INITIAL_STATE: SearchState = { q: "", mode: "native", sort: "relevance", page: 1 };

/** Thrown for an action that cannot be applied. Never swallowed into a silent no-op (guarantee 6). */
export class SearchStateError extends Error {
  override name = "SearchStateError";
}

// ---------------------------------------------------------------------------------------------------------
// URL → state and back

/** Why a URL parameter was not taken as written. Shown to the reader; invalid input never falls back silently. */
export interface UrlNotice {
  readonly param: string;
  readonly value: string;
  readonly reason: "unknown_param" | "invalid_value" | "repeated_param";
  /** The value used instead, when there is one. */
  readonly used?: string;
}

const KNOWN_PARAMS = ["q", "mode", "sort", "page"] as const;
type KnownParam = (typeof KNOWN_PARAMS)[number];

function isKnownParam(name: string): name is KnownParam {
  return (KNOWN_PARAMS as readonly string[]).includes(name);
}

function isMode(value: string): value is Mode {
  return (MODES as readonly string[]).includes(value);
}

function isSort(value: string): value is Sort {
  return (SORTS as readonly string[]).includes(value);
}

function isPage(page: number): boolean {
  return Number.isInteger(page) && page >= 1 && page <= MAX_PAGE;
}

function parsePage(value: string): number | null {
  if (!/^[1-9][0-9]{0,8}$/.test(value)) return null;
  const page = Number(value);
  return isPage(page) ? page : null;
}

export function fromURL(params: URLSearchParams): { state: SearchState; notices: UrlNotice[] } {
  const notices: UrlNotice[] = [];
  const first = new Map<KnownParam, string>();
  for (const [name, value] of params) {
    if (!isKnownParam(name)) {
      notices.push({ param: name, value, reason: "unknown_param" });
    } else if (first.has(name)) {
      notices.push({ param: name, value, reason: "repeated_param", used: first.get(name) ?? "" });
    } else {
      first.set(name, value);
    }
  }

  const q = first.get("q") ?? INITIAL_STATE.q;

  let mode = INITIAL_STATE.mode;
  const rawMode = first.get("mode");
  if (rawMode !== undefined) {
    if (isMode(rawMode)) mode = rawMode;
    else notices.push({ param: "mode", value: rawMode, reason: "invalid_value", used: mode });
  }

  let sort = INITIAL_STATE.sort;
  const rawSort = first.get("sort");
  if (rawSort !== undefined) {
    if (isSort(rawSort)) sort = rawSort;
    else notices.push({ param: "sort", value: rawSort, reason: "invalid_value", used: sort });
  }

  let page = INITIAL_STATE.page;
  const rawPage = first.get("page");
  if (rawPage !== undefined) {
    const parsed = parsePage(rawPage);
    if (parsed !== null) page = parsed;
    else notices.push({ param: "page", value: rawPage, reason: "invalid_value", used: String(page) });
  }

  return { state: { q, mode, sort, page }, notices };
}

/** Canonical URL parameters: `q` and `mode` always (they define the set); `sort`/`page` when not default. */
export function toURL(state: SearchState): URLSearchParams {
  const params = new URLSearchParams();
  params.set("q", state.q);
  params.set("mode", state.mode);
  if (state.sort !== INITIAL_STATE.sort) params.set("sort", state.sort);
  if (state.page !== INITIAL_STATE.page) params.set("page", String(state.page));
  return params;
}

export function searchHref(state: SearchState): string {
  return `/search?${toURL(state).toString()}`;
}

/** What decides membership. Two states with equal keys show the same result set, in any sort or page. */
export function resultSetKey(state: SearchState): readonly [q: string, mode: Mode] {
  return [state.q, state.mode];
}

/** The `GET /search` parameters (spec 04) for a state. */
export function toSearchRequest(state: SearchState): {
  q: string;
  mode: Mode;
  sort: Sort;
  offset: number;
  limit: number;
} {
  return {
    q: state.q,
    mode: state.mode,
    sort: state.sort,
    offset: (state.page - 1) * PAGE_SIZE,
    limit: PAGE_SIZE,
  };
}

// ---------------------------------------------------------------------------------------------------------
// Actions

export type FilterField = "venue" | "track" | "status";

/**
 * A field's single top-level filter clause, as the server's `/parse` reported it for `(source, mode)`.
 * - `field` and `negated: false`: the clause's field and polarity. A clause for another field, or a
 *   negated one (`-track:workshop`: adding `main` inside it would flip its meaning), is refused.
 * - `source` and `mode`: the query it was parsed from, keyed like `resultSetKey`; a stale clause is refused.
 * - `span`: code points into `source`. An applied default (spec 02: inserted defaults have the zero-width
 *   span `(len(q), len(q))`) or an unrestricted field is a zero-width span at the end, and the clause is
 *   then written out explicitly: `(q) AND field:(…)`.
 * - `values`: the values that clause admits (for a default, the default values; for an unrestricted
 *   field, every value in `/meta`), in the order to keep them.
 * TODO(TASK-078): derive this from the generated `/parse` schema once it reports clause spans.
 */
export interface FilterClause {
  readonly field: FilterField;
  readonly negated: false;
  readonly source: string;
  readonly mode: Mode;
  readonly span: CodePointSpan;
  readonly values: readonly string[];
}

export type SearchAction =
  | { readonly type: "submit"; readonly q: string; readonly mode?: Mode }
  | { readonly type: "builderEdit"; readonly q: string }
  | { readonly type: "setMode"; readonly mode: Mode }
  | {
      readonly type: "facetToggle";
      readonly field: FilterField;
      readonly value: string;
      readonly clause: FilterClause;
    }
  | {
      readonly type: "includeExcluded";
      readonly field: "track" | "status";
      readonly value: string;
      readonly clause: FilterClause;
    }
  | { readonly type: "sort"; readonly sort: Sort }
  | { readonly type: "page"; readonly page: number };

/** Taxonomy values (spec 01) are bare identifiers; anything else would need quoting the client can't judge. */
const FILTER_VALUE = /^[A-Za-z0-9_]+$/;

function formatClause(field: FilterField, values: readonly string[]): string {
  const only = values.length === 1 ? values[0] : undefined;
  return only !== undefined ? `${field}:${only}` : `${field}:(${values.join(" OR ")})`;
}

/** A query ending in an odd run of backslashes: the last one would escape a `)` written after it (spec 02). */
function endsInEscape(q: string): boolean {
  const run = /\\+$/.exec(q)?.[0].length ?? 0;
  return run % 2 === 1;
}

function rewriteClause(
  state: SearchState,
  field: FilterField,
  clause: FilterClause,
  values: readonly string[],
): string {
  const { q } = state;
  const [stateQ, stateMode] = resultSetKey(state);
  if (clause.source !== stateQ || clause.mode !== stateMode) {
    throw new SearchStateError("the filter clause was parsed from a different query or mode; re-parse first");
  }
  if (clause.field !== field) {
    throw new SearchStateError(`a ${clause.field} clause cannot be edited as ${field}`);
  }
  // Checked at runtime too: a caller holding untyped /parse data could pass `negated: true`.
  if ((clause.negated as boolean) !== false) {
    throw new SearchStateError(`the ${field} clause is negated; editing its values would flip its meaning`);
  }
  for (const v of [...clause.values, ...values]) {
    if (!FILTER_VALUE.test(v)) throw new SearchStateError(`not a ${field} value: ${JSON.stringify(v)}`);
  }
  if (values.length === 0) {
    throw new SearchStateError(`removing the last ${field} value would exclude every record`);
  }
  const text = formatClause(field, values);
  const [start, end] = clause.span;
  const qLength = codePointLength(q);
  if (start === end) {
    if (end !== qLength) throw new SearchStateError("a zero-width clause span must be at the end of q");
    if (q.trim() === "") return text;
    if (endsInEscape(q)) {
      throw new SearchStateError("q ends in an escaping backslash, which would swallow the closing ')'");
    }
    return `(${q}) AND ${text}`;
  }
  let utf16: readonly [number, number];
  try {
    utf16 = codePointSpanToUtf16(q, clause.span);
  } catch (e) {
    throw new SearchStateError(e instanceof Error ? e.message : String(e));
  }
  return q.slice(0, utf16[0]) + text + q.slice(utf16[1]);
}

export function reduce(state: SearchState, action: SearchAction): SearchState {
  switch (action.type) {
    case "submit":
      return { ...state, q: action.q, mode: action.mode ?? state.mode, page: 1 };
    case "builderEdit":
      return { ...state, q: action.q, page: 1 };
    case "setMode":
      return { ...state, mode: action.mode, page: 1 };
    case "facetToggle": {
      const { values } = action.clause;
      const next = values.includes(action.value)
        ? values.filter((v) => v !== action.value)
        : [...values, action.value];
      return { ...state, q: rewriteClause(state, action.field, action.clause, next), page: 1 };
    }
    case "includeExcluded": {
      const { values } = action.clause;
      if (values.includes(action.value)) {
        throw new SearchStateError(`${action.field}:${action.value} is already included`);
      }
      const next = [...values, action.value];
      return { ...state, q: rewriteClause(state, action.field, action.clause, next), page: 1 };
    }
    case "sort":
      return { ...state, sort: action.sort, page: 1 };
    case "page":
      if (!isPage(action.page)) {
        throw new SearchStateError(`not a page number: ${action.page}`);
      }
      return { ...state, page: action.page };
  }
}
