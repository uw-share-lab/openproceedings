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

/**
 * Longest `q` in code points. Mirrors the API parser's `MAX_QUERY_LENGTH` (spec 02 §Error handling; a longer
 * `q` is `PARSE_TOO_LONG`, a 422, and so is one whose canonical form is longer (decision-008), which only the
 * server can judge). `/meta` does not serve it yet, so keep the two equal by hand.
 */
export const MAX_QUERY_LENGTH = 2000;

export interface SearchState {
  readonly q: string;
  readonly mode: Mode;
  readonly sort: Sort;
  readonly page: number;
}

export const INITIAL_STATE: SearchState = { q: "", mode: "native", sort: "relevance", page: 1 };

/** Why an action cannot be applied. Controls branch on the code; the message is for the reader. */
export type SearchStateErrorCode =
  | "STALE_CLAUSE"
  | "WRONG_FIELD"
  | "NEGATED_CLAUSE"
  | "BAD_VALUE"
  | "LAST_VALUE"
  | "BAD_SPAN"
  | "TRAILING_ESCAPE"
  | "ALREADY_INCLUDED"
  | "NO_EDITABLE_CLAUSE"
  | "EMPTY_QUERY"
  | "TOO_LONG"
  | "BAD_PAGE";

/**
 * Thrown for an action that cannot be applied. Never swallowed into a silent no-op (guarantee 6).
 * Messages follow the ux-writing pattern: what happened — why. How to fix.
 */
export class SearchStateError extends Error {
  override name = "SearchStateError";
  constructor(
    readonly code: SearchStateErrorCode,
    message: string,
  ) {
    super(message);
  }
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

/** "a whole number from 1 to 10,000": the valid `page` values, in words, from `MAX_PAGE`. */
export const PAGE_RANGE_TEXT = `a whole number from 1 to ${MAX_PAGE.toLocaleString("en-US")}`;

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

  // q and mode say what was searched, so their notices come first; the sort is stable within a param.
  const rank = (n: UrlNotice) => (n.param === "q" ? 0 : n.param === "mode" ? 1 : 2);
  notices.sort((a, b) => rank(a) - rank(b));
  return { state: { q, mode, sort, page }, notices };
}

/** A notice as text runs; `code` runs are URL values, shown in monospace and quoted in plain text. */
export type NoticeRun = { readonly text: string } | { readonly code: string };

const codeList = (values: readonly string[]): NoticeRun[] =>
  values.flatMap((v, i) => [...(i === 0 ? [] : [{ text: ", " }]), { code: v }]);

/**
 * The reader-facing sentence for a URL notice (ux-writing: what happened — why. What was used instead).
 * An empty value is written `""`, so it cannot be mistaken for a missing one. Valid values come from the
 * same constants the reducer checks against.
 */
export function describeNotice(n: UrlNotice): NoticeRun[] {
  const shown = (v: string) => (v === "" ? '""' : v);
  switch (n.reason) {
    case "unknown_param":
      return [
        { code: `${n.param}=${n.value}` },
        { text: " was ignored — " },
        { code: n.param },
        { text: " is not a search parameter. Search parameters are " },
        ...codeList(KNOWN_PARAMS),
        { text: "." },
      ];
    case "repeated_param":
      return [
        { code: n.param },
        { text: " appears more than once; using the first value " },
        { code: shown(n.used ?? "") },
        { text: " and ignoring " },
        { code: shown(n.value) },
        { text: "." },
      ];
    case "invalid_value": {
      const head: NoticeRun[] = [{ code: `${n.param}=${n.value}` }];
      const used = n.used ?? "";
      if (n.param === "mode") {
        return [
          ...head,
          { text: " is not a mode — modes are " },
          ...codeList(MODES),
          { text: ". " },
          { code: "q" },
          { text: ` was read as ${used} syntax.` },
        ];
      }
      if (n.param === "sort") {
        return [
          ...head,
          { text: " is not a sort order — sort orders are " },
          ...codeList(SORTS),
          { text: ". Sorted by " },
          { code: used },
          { text: " instead." },
        ];
      }
      return [
        ...head,
        { text: ` is not a page number — a page is ${PAGE_RANGE_TEXT}. Showing page ${used} instead.` },
      ];
    }
  }
}

/** `describeNotice` as plain text, code runs in backticks (logs, copied text, tests). */
export function noticeText(n: UrlNotice): string {
  return describeNotice(n)
    .map((r) => ("code" in r ? `\`${r.code}\`` : r.text))
    .join("");
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
 * "Top-level" is judged on the flattened canonical tree: parenthesised AND groups are flattened, so in
 * `track:workshop llm AND (venue:NeurIPS track:workshop)` both `track:` clauses are top-level. A field
 * with more than one such clause (or one only inside an OR or NOT) has no editable clause: `/parse` says
 * so and the action carries `clause: null`, which the reducer refuses (`NO_EDITABLE_CLAUSE`). Splicing
 * over one of two clauses would leave the other ANDed in, so the edit would silently change nothing.
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
      /** `null`: `/parse` reported no single editable clause for the field. */
      readonly clause: FilterClause | null;
    }
  | {
      readonly type: "includeExcluded";
      readonly field: "track" | "status";
      readonly value: string;
      /** `null`: `/parse` reported no single editable clause for the field. */
      readonly clause: FilterClause | null;
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

/** The clause, or NO_EDITABLE_CLAUSE when `/parse` reported none that can be edited. */
function editable(field: FilterField, clause: FilterClause | null): FilterClause {
  if (clause !== null) return clause;
  throw new SearchStateError(
    "NO_EDITABLE_CLAUSE",
    `The ${field} filter cannot be changed here — the query has more than one top-level \`${field}:\` clause, ` +
      "or one inside an OR or NOT. Edit it in the query text.",
  );
}

function rewriteClause(
  state: SearchState,
  field: FilterField,
  clause: FilterClause,
  values: readonly string[],
): string {
  const next = spliceClause(state, field, clause, values);
  const length = codePointLength(next);
  if (length > MAX_QUERY_LENGTH) {
    throw new SearchStateError(
      "TOO_LONG",
      `The changed query would be ${length.toLocaleString("en-US")} characters long — the limit is ` +
        `${MAX_QUERY_LENGTH.toLocaleString("en-US")}. Shorten the query text first.`,
    );
  }
  return next;
}

function spliceClause(
  state: SearchState,
  field: FilterField,
  clause: FilterClause,
  values: readonly string[],
): string {
  const { q } = state;
  const [stateQ, stateMode] = resultSetKey(state);
  if (clause.source !== stateQ || clause.mode !== stateMode) {
    throw new SearchStateError(
      "STALE_CLAUSE",
      `The ${field} filter was read from an earlier query — the query or mode changed after it was parsed. ` +
        "Wait for the current query to be parsed, then try again.",
    );
  }
  if (clause.field !== field) {
    throw new SearchStateError(
      "WRONG_FIELD",
      `This is a \`${clause.field}:\` clause, not \`${field}:\` — a clause is only edited as its own field. ` +
        `Use the \`${field}:\` clause from the parse result.`,
    );
  }
  // Checked at runtime too: a caller holding untyped /parse data could pass `negated: true`.
  if ((clause.negated as boolean) !== false) {
    throw new SearchStateError(
      "NEGATED_CLAUSE",
      `The \`${field}:\` clause is negated — changing its values would flip which papers it removes. ` +
        "Edit it in the query text instead.",
    );
  }
  for (const v of [...clause.values, ...values]) {
    if (!FILTER_VALUE.test(v)) {
      throw new SearchStateError(
        "BAD_VALUE",
        `\`${v}\` is not a ${field} value — ${field} values are single words of letters, digits and \`_\`. ` +
          "Use a value listed by /meta.",
      );
    }
  }
  if (values.length === 0) {
    throw new SearchStateError(
      "LAST_VALUE",
      `Removing the last ${field} value would exclude every record — the \`${field}:\` clause would admit nothing. ` +
        "Select another value first.",
    );
  }
  const text = formatClause(field, values);
  const [start, end] = clause.span;
  const qLength = codePointLength(q);
  if (start === end) {
    if (end !== qLength) {
      throw new SearchStateError(
        "BAD_SPAN",
        `The ${field} filter's span [${start}, ${end}) is empty but not at the end of q — only an applied ` +
          "default has an empty span, at the end. Parse the query again.",
      );
    }
    // Unreachable through /parse (an empty query is a parse error, so no clause is reported), but an
    // empty q would otherwise be wrapped into the empty group `()`.
    if (q.trim() === "") {
      throw new SearchStateError(
        "EMPTY_QUERY",
        "The query is empty — there is nothing to add the filter to. Type a query first.",
      );
    }
    if (endsInEscape(q)) {
      throw new SearchStateError(
        "TRAILING_ESCAPE",
        "The query ends in an escaping backslash — it would escape the `)` added after it. " +
          "Remove the backslash, or write it as `\\\\`.",
      );
    }
    return `(${q}) AND ${text}`;
  }
  let utf16: readonly [number, number];
  try {
    utf16 = codePointSpanToUtf16(q, clause.span);
  } catch (e) {
    throw new SearchStateError(
      "BAD_SPAN",
      `The ${field} filter's span does not fit the query — ${e instanceof Error ? e.message : String(e)}. ` +
        "Parse the query again.",
    );
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
      const clause = editable(action.field, action.clause);
      const { values } = clause;
      const next = values.includes(action.value)
        ? values.filter((v) => v !== action.value)
        : [...values, action.value];
      return { ...state, q: rewriteClause(state, action.field, clause, next), page: 1 };
    }
    case "includeExcluded": {
      const clause = editable(action.field, action.clause);
      const { values } = clause;
      if (values.includes(action.value)) {
        throw new SearchStateError(
          "ALREADY_INCLUDED",
          `\`${action.field}:${action.value}\` is already included — the \`${action.field}:\` clause admits it. ` +
            "Nothing needs to change.",
        );
      }
      const next = [...values, action.value];
      return { ...state, q: rewriteClause(state, action.field, clause, next), page: 1 };
    }
    case "sort":
      return { ...state, sort: action.sort, page: 1 };
    case "page":
      if (!isPage(action.page)) {
        throw new SearchStateError(
          "BAD_PAGE",
          `${action.page} is not a page number — a page is ${PAGE_RANGE_TEXT}. Choose a page in that range.`,
        );
      }
      return { ...state, page: action.page };
  }
}

/**
 * Why `action` cannot be applied to `state`, or `null` if it can. Controls that dispatch a clause rewrite
 * (facet toggles, include buttons) call this while rendering and are disabled with the message as their
 * description, instead of being refused after the click (spec 05 §URL is state). `STALE_CLAUSE` is the
 * usual case: the query changed and `/parse` has not answered for it yet.
 */
export function whyBlocked(state: SearchState, action: SearchAction): SearchStateError | null {
  try {
    reduce(state, action);
    return null;
  } catch (e) {
    if (e instanceof SearchStateError) return e;
    throw e;
  }
}
