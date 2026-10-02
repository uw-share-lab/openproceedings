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
import type { components } from "@/api/schema";
import { codePointLength, codePointSpanToUtf16 } from "@/api/spans";
import { clip } from "./clip";
import defaultLimits from "./default-limits.json";

export const MODES = ["native", "scholar"] as const;
export type Mode = (typeof MODES)[number];

/** Spec 03 §Ranking. `semantic` (deferred) joins when spec 06 is enabled. */
export const SORTS = ["relevance", "year_desc", "year_asc", "title"] as const;
export type Sort = (typeof SORTS)[number];

/** Results per page; the API's `limit` (spec 03 default 50, spec 04 max 200). */
export const PAGE_SIZE = 50;

/** Highest page the URL may name: offsets stay under 500,000, several times the whole corpus. */
export const MAX_PAGE = 10_000;

/**
 * The limits the reducer checks: `max_query_length`, the longest `q` in code points (spec 02 §Error handling;
 * a longer `q` is `PARSE_TOO_LONG`, a 422, and so is one whose canonical form is longer (decision-008), which
 * only the server can judge), and `max_query_depth`, the deepest nesting of groups and `NOT`s (`PARSE_TOO_DEEP`),
 * which words `/parse`'s `too_deep` refusal. The type is `/meta`'s `limits` (TASK-089), so it follows the
 * contract.
 */
export type QueryLimits = Pick<components["schemas"]["Limits"], "max_query_length" | "max_query_depth">;

/**
 * The limits to use until `/meta` is fetched (TASK-041/042 wire the fetch; then pass its `limits` to `reduce`
 * and `whyBlocked`). The value is `default-limits.json`, which the backend's contract test
 * (`test_meta_limits.py`) checks against the caps `/meta` serves, so it can't drift from the parser.
 */
export const DEFAULT_LIMITS: QueryLimits = {
  max_query_length: defaultLimits.max_query_length,
  max_query_depth: defaultLimits.max_query_depth,
};

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
  | "NOT_INCLUDED"
  | "TOO_MANY_RANGES"
  | "NO_EDITABLE_CLAUSE"
  | "EMPTY_QUERY"
  | "TOO_LONG"
  | "TOO_DEEP"
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

/**
 * A notice as text runs; `code` runs are URL values, shown in monospace and quoted in plain text. A value
 * from the URL is shown through `clip` (TASK-144): one visible line, its backticks escaped.
 */
export type NoticeRun = { readonly text: string } | { readonly code: string };

const codeList = (values: readonly string[]): NoticeRun[] =>
  values.flatMap((v, i) => [...(i === 0 ? [] : [{ text: ", " }]), { code: v }]);

/** A value as a message quotes it: through `clip`, and an empty one as `""` so it can't read as missing. */
const shown = (v: string): string => (v === "" ? '""' : clip(v));

/** At most how many code points of context `apart` keeps before the first difference. */
const APART_CONTEXT = 10;

/**
 * Two values as a notice quotes them side by side. Clipped alike they could read the same (two long `q`
 * values that differ only after the first 40 code points), so then each is shown from a little before the
 * first difference, a cut start marked `…`: the most context, up to `APART_CONTEXT`, that still shows them
 * apart (escapes are wide). Values that still read alike (they differ only in whitespace) are shown as is.
 */
function apart(a: string, b: string): readonly [string, string] {
  const plain = [shown(a), shown(b)] as const;
  // only values clip shortened can hide their difference; shorter ones differ only in whitespace
  if (a === b || plain[0] !== plain[1] || !plain[0].endsWith("…")) return plain;
  const [x, y] = [[...a], [...b]];
  let i = 0;
  while (x[i] === y[i]) i += 1;
  const from = (cps: readonly string[], start: number) =>
    start > 0 ? `…${clip(cps.slice(start).join(""), 39)}` : clip(cps.join(""));
  for (let back = APART_CONTEXT; back >= 0; back -= 1) {
    const start = Math.max(0, i - back);
    const pair = [from(x, start), from(y, start)] as const;
    if (pair[0] !== pair[1]) return pair;
  }
  return plain;
}

/**
 * The reader-facing sentence for a URL notice (ux-writing: what happened — why. What was used instead).
 * An empty value is written `""`, so it cannot be mistaken for a missing one. Valid values come from the
 * same constants the reducer checks against.
 */
export function describeNotice(n: UrlNotice): NoticeRun[] {
  switch (n.reason) {
    case "unknown_param":
      return [
        { code: `${shown(n.param)}=${clip(n.value)}` },
        { text: " was ignored — " },
        { code: shown(n.param) },
        { text: " is not a search parameter. Search parameters are " },
        ...codeList(KNOWN_PARAMS),
        { text: "." },
      ];
    case "repeated_param": {
      const [used, ignored] = apart(n.used ?? "", n.value);
      return [
        { code: n.param },
        { text: " appears more than once; using the first value " },
        { code: used },
        { text: " and ignoring " },
        { code: ignored },
        { text: "." },
      ];
    }
    case "invalid_value": {
      const head: NoticeRun[] = [{ code: `${n.param}=${clip(n.value)}` }];
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

/** One filter field's clause as `POST /parse` reports it in `filters` (spec 02 §Filter clauses; generated). */
export type ParsedClause = components["schemas"]["ParsedClause"];
export type ParsedFilters = components["schemas"]["ParsedFilters"];

/**
 * Why `/parse` reported a field's clause as not toggleable. An open set (decision-009): a reason this code
 * doesn't know is worded generically, never assumed away.
 */
export type ClauseReason = NonNullable<ParsedClause["reason"]>;

/** The fields a click edits: the `filters` keys whose clause is a value list (`year` is ranges). */
export type FilterField = {
  [K in keyof ParsedFilters]: ParsedFilters[K] extends ParsedClause ? K : never;
}[keyof ParsedFilters];

const FILTER_FIELDS: readonly FilterField[] = ["venue", "track", "status"];

function isFilterField(field: string): field is FilterField {
  return (FILTER_FIELDS as readonly string[]).includes(field);
}

/**
 * A field's single top-level filter clause, as the server's `/parse` reported it for `(source, mode)`: the
 * generated `ParsedClause` narrowed to one a click may rewrite (`clauseFromParse` builds it), keyed by the
 * query it was parsed from. "Top-level" is judged on the flattened canonical tree: parenthesised AND groups
 * are flattened, so in `track:workshop llm AND (venue:NeurIPS track:workshop)` both `track:` clauses are
 * top-level. A field with more than one such clause (or one only inside an OR or NOT) has no editable
 * clause: `/parse` says so with a `reason`, and the action carries `clause: null`, which the reducer refuses
 * (`NO_EDITABLE_CLAUSE`, or the reason's own code). Splicing over one of two clauses would leave the other
 * ANDed in, so the edit would silently change nothing.
 * - `field` and `negated: false`: the clause's field and polarity. A clause for another field, or a
 *   negated one (`-track:workshop`: adding `main` inside it would flip its meaning), is refused.
 * - `source` and `mode`: the query it was parsed from, keyed like `resultSetKey`; a stale clause is refused.
 * - `span`: code points into `source`. An applied default (spec 02: inserted defaults have the zero-width
 *   span `(len(q), len(q))`) or an unrestricted field is a zero-width span at the end, and the clause is
 *   then written out explicitly: `(q) AND field:(…)`.
 * - `values`: the values that clause admits (for a default, the default values; for an unrestricted
 *   field, every value), in the order to keep them.
 */
export type FilterClause = Readonly<{
  field: FilterField;
  negated: false;
  source: string;
  mode: Mode;
  span: Readonly<NonNullable<ParsedClause["span"]>>;
  values: Readonly<NonNullable<ParsedClause["values"]>>;
}>;

/** What a click action carries about its field's clause: the clause, or none and `/parse`'s reason. */
export interface ClauseChoice {
  readonly clause: FilterClause | null;
  /** Why there is no clause; `null` when `/parse` gave none (the query did not parse). */
  readonly reason: ClauseReason | null;
}

/**
 * The clause a click on a field may rewrite, from `/parse`'s report for that field (`filters[field]`;
 * `null` or `undefined` when the query did not parse) and the `(source, mode)` it was parsed from. Spread
 * the result into a `facetToggle` or `includeExcluded` action. Only a toggleable, positive clause with a
 * span is returned; otherwise `clause` is `null` with the server's reason.
 */
export function clauseFromParse(
  parsed: ParsedClause | null | undefined,
  source: string,
  mode: Mode,
): ClauseChoice {
  if (parsed === null || parsed === undefined) return { clause: null, reason: null };
  const { field, negated, span, values, toggleable, reason } = parsed;
  if (!toggleable || negated || span === null || values === null || !isFilterField(field)) {
    return { clause: null, reason };
  }
  return { clause: { field, negated, source, mode, span, values }, reason: null };
}

/** `/parse`'s `year` report: ranges, not a value list (spec 02 §Filter clauses; generated). */
export type ParsedYearClause = components["schemas"]["ParsedYearClause"];
export type YearRange = components["schemas"]["YearRange"];

/** The years a query may name: `year:` takes four-digit years (spec 02; the parser's `MIN_YEAR`/`MAX_YEAR`). */
export const MIN_YEAR = 1000;
export const MAX_YEAR = 9999;

/**
 * The most ranges a year action writes. `/parse` checks the year clause's widest edit as this many
 * full-width ranges (`query/clauses.py::MAX_YEAR_RANGES`), so every edit within it is one the server has
 * already judged; a year clause with more is edited in the query text (`TOO_MANY_RANGES`). The two constants
 * are tied by `year-clause-golden.json`, which both sides' tests read.
 */
export const MAX_YEAR_RANGES = 4;

/** Every year: what an unrestricted `year` admits, and what clearing the year filter writes. */
export const EVERY_YEAR: YearRange = { lo: MIN_YEAR, hi: MAX_YEAR };

/**
 * The year clause a year action may rewrite: the generated `ParsedYearClause` narrowed as `FilterClause` is
 * (positive, toggleable, with a span), keyed by the `(source, mode)` it was parsed from. `ranges` are the
 * years it admits, sorted and merged; `1000..9999` for no restriction (a zero-width span at the end, written
 * out as `(q) AND year:(…)`).
 */
export type YearClause = Readonly<{
  field: "year";
  negated: false;
  source: string;
  mode: Mode;
  span: Readonly<NonNullable<ParsedYearClause["span"]>>;
  ranges: readonly Readonly<YearRange>[];
}>;

/** What a year action carries about the year clause: the clause, or none and `/parse`'s reason. */
export interface YearClauseChoice {
  readonly clause: YearClause | null;
  /** Why there is no clause; `null` when `/parse` gave none (the query did not parse). */
  readonly reason: ClauseReason | null;
}

/**
 * The year clause a year action may rewrite, from `/parse`'s `filters.year` and the `(source, mode)` it was
 * parsed from: `clauseFromParse` for ranges. Spread the result into a year action.
 */
export function yearClauseFromParse(
  parsed: ParsedYearClause | null | undefined,
  source: string,
  mode: Mode,
): YearClauseChoice {
  if (parsed === null || parsed === undefined) return { clause: null, reason: null };
  const { field, negated, span, ranges, toggleable, reason } = parsed;
  if (!toggleable || negated || span === null || ranges === null || field !== "year") {
    return { clause: null, reason };
  }
  return { clause: { field, negated, source, mode, span, ranges }, reason: null };
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
      /** `/parse`'s reason when `clause` is `null` (`clauseFromParse`); it words the refusal. */
      readonly reason?: ClauseReason | null;
    }
  | {
      readonly type: "includeExcluded";
      readonly field: "track" | "status";
      readonly value: string;
      /** `null`: `/parse` reported no single editable clause for the field. */
      readonly clause: FilterClause | null;
      /** `/parse`'s reason when `clause` is `null` (`clauseFromParse`); it words the refusal. */
      readonly reason?: ClauseReason | null;
    }
  | YearAction
  | { readonly type: "sort"; readonly sort: Sort }
  | { readonly type: "page"; readonly page: number };

/**
 * An edit of the year filter. Each writes the whole year clause, grouped and merged as the canonical form
 * keeps it (`year:(2020..2022 OR 2024)`), over `/parse`'s year clause (`yearClauseFromParse`):
 * - `yearSet`: exactly `range`;
 * - `yearClear`: every year, `year:(1000..9999)` (the clause is rewritten, never deleted: deleting it could
 *   leave an operator with nothing after it);
 * - `yearAdd`: the clause's years and `range`;
 * - `yearRemove`: the clause's years without `range`.
 */
export type YearAction = (
  | { readonly type: "yearSet"; readonly range: YearRange }
  | { readonly type: "yearClear" }
  | { readonly type: "yearAdd"; readonly range: YearRange }
  | { readonly type: "yearRemove"; readonly range: YearRange }
) & {
  /** `null`: `/parse` reported no single editable year clause. */
  readonly clause: YearClause | null;
  /** `/parse`'s reason when `clause` is `null` (`yearClauseFromParse`); it words the refusal. */
  readonly reason?: ClauseReason | null;
};

/** Taxonomy values (spec 01) are bare identifiers; anything else would need quoting the client can't judge. */
const FILTER_VALUE = /^[A-Za-z0-9_]+$/;

/**
 * A clause as the reducer writes it: always grouped, `field:(v)` even for one value (the server's
 * `query/clauses.py::_format`). A bare `field:v` spliced before a group would touch it
 * (`track:workshop(x OR y)` is PARSE_PAREN_TOUCHES_WORD); the group's `)` never does, and the canonical form
 * (and so the hash) is the same either way.
 */
function formatClause(field: FilterField, values: readonly string[]): string {
  return `${field}:(${values.join(" OR ")})`;
}

/** A query ending in an odd run of backslashes: the last one would escape a `)` written after it (spec 02). */
function endsInEscape(q: string): boolean {
  const run = /\\+$/.exec(q)?.[0].length ?? 0;
  return run % 2 === 1;
}

/** A field a clause rewrite edits: a value-list field, or `year`. */
type ClauseField = FilterField | "year";

function negatedClause(field: ClauseField): SearchStateError {
  return new SearchStateError(
    "NEGATED_CLAUSE",
    `The \`${clip(field)}:\` clause is negated — changing its values would flip which papers it removes. ` +
      "Edit it in the query text instead.",
  );
}

/** The refusal for a field `/parse` reported no editable clause for, worded from its reason. */
function noEditableClause(
  field: ClauseField,
  reason: ClauseReason | null | undefined,
  limits: QueryLimits,
): SearchStateError {
  const head = `The ${clip(field)} filter cannot be changed here — `;
  const refuse = (why: string) =>
    new SearchStateError("NO_EDITABLE_CLAUSE", `${head}${why} Edit it in the query text.`);
  switch (reason) {
    case "negated":
      return negatedClause(field);
    case "too_long":
      return new SearchStateError(
        "TOO_LONG",
        `${head}written out in full, the changed query would be over the ` +
          `${limits.max_query_length.toLocaleString("en-US")}-character limit. Shorten the query text first.`,
      );
    case "too_deep":
      return new SearchStateError(
        "TOO_DEEP",
        `${head}the changed query would nest groups or NOTs more than ${limits.max_query_depth} deep. ` +
          "Remove a level of parentheses first.",
      );
    case "multiple_clauses":
      return refuse(`the query has more than one top-level \`${clip(field)}:\` clause.`);
    case "nested":
      return refuse(`its only \`${clip(field)}:\` clause is inside an OR or NOT.`);
    case "mixed_fields":
      return refuse(`its \`${clip(field)}:\` clause is ORed with another field's clause.`);
    case "unparsable_edit":
      return refuse("the changed query would not parse.");
    default: // no reason given, or one this code doesn't know (an open set)
      return refuse(
        `the query has more than one top-level \`${clip(field)}:\` clause, or one inside an OR or NOT.`,
      );
  }
}

/** The clause, or the refusal `/parse`'s reason calls for when it reported none that can be edited. */
function editable<C>(
  field: ClauseField,
  clause: C | null,
  reason: ClauseReason | null | undefined,
  limits: QueryLimits,
): C {
  if (clause !== null) return clause;
  throw noEditableClause(field, reason, limits);
}

/** The new `q`, refused when it is over the instance's length limit. */
function withinLength(next: string, limits: QueryLimits): string {
  const length = codePointLength(next);
  if (length > limits.max_query_length) {
    throw new SearchStateError(
      "TOO_LONG",
      `The changed query would be ${length.toLocaleString("en-US")} characters long — the limit is ` +
        `${limits.max_query_length.toLocaleString("en-US")}. Shorten the query text first.`,
    );
  }
  return next;
}

function rewriteClause(
  state: SearchState,
  field: FilterField,
  clause: FilterClause,
  values: readonly string[],
  limits: QueryLimits,
): string {
  return withinLength(spliceClause(state, field, clause, values), limits);
}

/** Refuses a clause parsed from another query or mode, of another field, or negated. */
function checkClause(state: SearchState, field: ClauseField, clause: FilterClause | YearClause): void {
  const [stateQ, stateMode] = resultSetKey(state);
  if (clause.source !== stateQ || clause.mode !== stateMode) {
    throw new SearchStateError(
      "STALE_CLAUSE",
      `The ${clip(field)} filter was read from an earlier query — the query or mode changed after it was ` +
        "parsed. Wait for the current query to be parsed, then try again.",
    );
  }
  if (clause.field !== field) {
    throw new SearchStateError(
      "WRONG_FIELD",
      `This is a \`${clip(clause.field)}:\` clause, not \`${clip(field)}:\` — a clause is only edited as its own ` +
        `field. Use the \`${clip(field)}:\` clause from the parse result.`,
    );
  }
  // Checked at runtime too: a caller holding untyped /parse data could pass `negated: true`.
  if ((clause.negated as boolean) !== false) throw negatedClause(field);
}

function spliceClause(
  state: SearchState,
  field: FilterField,
  clause: FilterClause,
  values: readonly string[],
): string {
  checkClause(state, field, clause);
  const name = clip(field);
  for (const v of [...clause.values, ...values]) {
    if (!FILTER_VALUE.test(v)) {
      throw new SearchStateError(
        "BAD_VALUE",
        `\`${shown(v)}\` is not a ${name} value — ${name} values are single words of letters, digits and \`_\`. ` +
          "Use a value listed by /meta.",
      );
    }
  }
  if (values.length === 0) {
    throw new SearchStateError(
      "LAST_VALUE",
      `Removing the last ${name} value would exclude every record — the \`${name}:\` clause would admit ` +
        "nothing. Select another value first.",
    );
  }
  return placeClause(state.q, field, clause.span, formatClause(field, values));
}

/**
 * `q` with `text` (a whole grouped clause) over the clause at code-point `span`, or, for the zero-width span
 * at the end (an applied default or an unrestricted field), `q` wrapped: `(q) AND text`.
 */
function placeClause(q: string, field: ClauseField, span: readonly [number, number], text: string): string {
  const [start, end] = span;
  const qLength = codePointLength(q);
  if (start === end) {
    if (end !== qLength) {
      throw new SearchStateError(
        "BAD_SPAN",
        `The ${clip(field)} filter's span [${clip(String(start))}, ${clip(String(end))}) is empty but not at ` +
          "the end of q — only an applied default has an empty span, at the end. Parse the query again.",
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
    utf16 = codePointSpanToUtf16(q, span);
  } catch (e) {
    throw new SearchStateError(
      "BAD_SPAN",
      `The ${clip(field)} filter's span does not fit the query — ` +
        `${clip(e instanceof Error ? e.message : String(e), 120)}. Parse the query again.`,
    );
  }
  return q.slice(0, utf16[0]) + text + q.slice(utf16[1]);
}

// ---------------------------------------------------------------------------------------------------------
// Year ranges: arithmetic on the ranges /parse reported (never a parse of `q`)

/** A range as the query writes it: `2024` for one year, `2020..2026` for more. */
export function formatYearRange(r: YearRange): string {
  return r.lo === r.hi ? String(r.lo) : `${r.lo}..${r.hi}`;
}

/**
 * The year clause as a year action writes it: always grouped, like every clause (`year:(2024)`), with the
 * ranges sorted and merged as the canonical form keeps them, so it is never longer than `/parse`'s widest
 * year edit.
 */
export function formatYearClause(ranges: readonly YearRange[]): string {
  return `year:(${ranges.map(formatYearRange).join(" OR ")})`;
}

function checkedRange(r: YearRange): YearRange {
  const year = (y: number) => Number.isInteger(y) && y >= MIN_YEAR && y <= MAX_YEAR;
  if (!year(r.lo) || !year(r.hi) || r.lo > r.hi) {
    throw new SearchStateError(
      "BAD_VALUE",
      `\`${clip(String(r.lo))}..${clip(String(r.hi))}\` is not a year range — a range runs from a ` +
        `four-digit year to the same or a later one, between ${MIN_YEAR} and ${MAX_YEAR}. ` +
        "Choose two years in that range, the earlier first.",
    );
  }
  return { lo: r.lo, hi: r.hi };
}

/** Sorted, with overlapping or adjacent ranges joined (`2020..2021` and `2022` are `2020..2022`). */
function mergeRanges(ranges: readonly YearRange[]): YearRange[] {
  const sorted = [...ranges].sort((a, b) => a.lo - b.lo || a.hi - b.hi);
  const out: YearRange[] = [];
  for (const r of sorted) {
    const last = out.at(-1);
    if (last !== undefined && r.lo <= last.hi + 1) {
      out[out.length - 1] = { lo: last.lo, hi: Math.max(last.hi, r.hi) };
    } else {
      out.push({ lo: r.lo, hi: r.hi });
    }
  }
  return out;
}

/** `ranges` (merged) without the years of `r`. */
function subtractRange(ranges: readonly YearRange[], r: YearRange): YearRange[] {
  return ranges.flatMap((m) => {
    if (m.hi < r.lo || m.lo > r.hi) return [m];
    return [
      ...(m.lo < r.lo ? [{ lo: m.lo, hi: r.lo - 1 }] : []),
      ...(r.hi < m.hi ? [{ lo: r.hi + 1, hi: m.hi }] : []),
    ];
  });
}

const sameRanges = (a: readonly YearRange[], b: readonly YearRange[]): boolean =>
  a.length === b.length && a.every((r, i) => r.lo === b[i]?.lo && r.hi === b[i]?.hi);

/** The ranges a year action leaves the clause admitting, or why it can't. */
function nextYearRanges(current: readonly YearRange[], action: YearAction): YearRange[] {
  const unchanged = (what: string, why: string) =>
    new SearchStateError("ALREADY_INCLUDED", `${what} — ${why}. Nothing needs to change.`);
  switch (action.type) {
    case "yearClear":
      if (sameRanges(current, [EVERY_YEAR])) {
        throw unchanged(
          "Every year is already included",
          `the \`year:\` clause admits ${MIN_YEAR} to ${MAX_YEAR}`,
        );
      }
      return [EVERY_YEAR];
    case "yearSet": {
      const r = checkedRange(action.range);
      if (sameRanges(current, [r])) {
        throw unchanged(
          `\`${formatYearRange(r)}\` is already the year filter`,
          "the `year:` clause admits exactly those years",
        );
      }
      return [r];
    }
    case "yearAdd": {
      const r = checkedRange(action.range);
      if (current.some((m) => m.lo <= r.lo && r.hi <= m.hi)) {
        throw unchanged(
          `\`${formatYearRange(r)}\` is already included`,
          "the `year:` clause admits every year in it",
        );
      }
      return mergeRanges([...current, r]);
    }
    case "yearRemove": {
      const r = checkedRange(action.range);
      const next = subtractRange(current, r);
      if (sameRanges(next, current)) {
        throw new SearchStateError(
          "NOT_INCLUDED",
          `\`${formatYearRange(r)}\` is not included — the \`year:\` clause admits none of those years. ` +
            "Nothing needs to change.",
        );
      }
      if (next.length === 0) {
        throw new SearchStateError(
          "LAST_VALUE",
          `Removing \`${formatYearRange(r)}\` would exclude every record — the \`year:\` clause would admit ` +
            "no year. Add another range first.",
        );
      }
      return next;
    }
  }
}

function rewriteYear(
  state: SearchState,
  clause: YearClause,
  action: YearAction,
  limits: QueryLimits,
): string {
  checkClause(state, "year", clause);
  const current = mergeRanges(clause.ranges.map(checkedRange));
  const next = nextYearRanges(current, action);
  if (next.length > MAX_YEAR_RANGES) {
    throw new SearchStateError(
      "TOO_MANY_RANGES",
      `The year filter would have ${next.length} separate ranges — a year control writes at most ` +
        `${MAX_YEAR_RANGES}. Join two ranges first, or edit \`year:\` in the query text.`,
    );
  }
  return withinLength(placeClause(state.q, "year", clause.span, formatYearClause(next)), limits);
}

/**
 * The next state after `action`, or a `SearchStateError` saying why it can't be applied. `limits` are the
 * instance's (`/meta`'s `limits`); `DEFAULT_LIMITS` until it is fetched.
 */
export function reduce(
  state: SearchState,
  action: SearchAction,
  limits: QueryLimits = DEFAULT_LIMITS,
): SearchState {
  switch (action.type) {
    case "submit":
      return { ...state, q: action.q, mode: action.mode ?? state.mode, page: 1 };
    case "builderEdit":
      return { ...state, q: action.q, page: 1 };
    case "setMode":
      return { ...state, mode: action.mode, page: 1 };
    case "facetToggle": {
      const clause = editable(action.field, action.clause, action.reason, limits);
      const { values } = clause;
      const next = values.includes(action.value)
        ? values.filter((v) => v !== action.value)
        : [...values, action.value];
      return { ...state, q: rewriteClause(state, action.field, clause, next, limits), page: 1 };
    }
    case "includeExcluded": {
      const clause = editable(action.field, action.clause, action.reason, limits);
      const { values } = clause;
      if (values.includes(action.value)) {
        throw new SearchStateError(
          "ALREADY_INCLUDED",
          `\`${clip(action.field)}:${clip(action.value)}\` is already included — the \`${clip(action.field)}:\` ` +
            "clause admits it. Nothing needs to change.",
        );
      }
      const next = [...values, action.value];
      return { ...state, q: rewriteClause(state, action.field, clause, next, limits), page: 1 };
    }
    case "yearSet":
    case "yearClear":
    case "yearAdd":
    case "yearRemove": {
      const clause = editable("year", action.clause, action.reason, limits);
      return { ...state, q: rewriteYear(state, clause, action, limits), page: 1 };
    }
    case "sort":
      return { ...state, sort: action.sort, page: 1 };
    case "page":
      if (!isPage(action.page)) {
        throw new SearchStateError(
          "BAD_PAGE",
          `${clip(String(action.page))} is not a page number — a page is ${PAGE_RANGE_TEXT}. ` +
            "Choose a page in that range.",
        );
      }
      return { ...state, page: action.page };
  }
}

/**
 * Why `action` cannot be applied to `state`, or `null` if it can. Controls that dispatch a clause rewrite
 * (facet toggles, include buttons, the year control) call this while rendering and are disabled with the message as their
 * description, instead of being refused after the click (spec 05 §URL is state). `STALE_CLAUSE` is the
 * usual case: the query changed and `/parse` has not answered for it yet.
 */
export function whyBlocked(
  state: SearchState,
  action: SearchAction,
  limits: QueryLimits = DEFAULT_LIMITS,
): SearchStateError | null {
  try {
    reduce(state, action, limits);
    return null;
  } catch (e) {
    if (e instanceof SearchStateError) return e;
    throw e;
  }
}
