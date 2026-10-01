/**
 * The methods text a search record generates (spec 05 §Components 8, verbatim; design §Methods text rules;
 * prisma-reporting skill). Pure: every number is a field of the record the API sent (`identified_total`,
 * `excluded`, `unclassified_total`, `total`), read, never added up; every clause is the server's `/parse`
 * report of the record's `canonical`, sliced from it, never a parse on the client.
 *
 * `methodsText` is only called for a citable record (`citabilityCaution` is null) whose replay isn't a
 * `mismatch`; the record page and the save panel check both first.
 */
import type { MethodResponse } from "openapi-fetch";
import type { Api } from "@/api/client";
import { codePointSpanToUtf16 } from "@/api/spans";
import type { ParseResponse } from "@/editor/parse";

export type RecordResponse = MethodResponse<Api, "get", "/api/v1/records/{id}">;
export type SearchRecord = RecordResponse["record"];

const num = (n: number) => n.toLocaleString("en-US");
const count = (n: number, one: string, many: string) => `${num(n)} ${n === 1 ? one : many}`;
const code = (text: string) => `\`${text}\``;

/** A timestamp's UTC date, `2026-09-25` (the API sends one `…Z` form; anything else is shown as sent). */
export function utcDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toISOString().slice(0, 10);
}

/**
 * The crawl window as the methods text words it, by `crawl_dates_kind["*"]` (spec 05 §Components 8; never
 * one date, never "a crawl" for Scholar's own search dates). `null` when the record has no `*` window.
 */
export function builtFrom(record: SearchRecord): string | null {
  const window = record.crawl_dates["*"];
  if (window === undefined) return null;
  const from = utcDate(window.from);
  const to = utcDate(window.to);
  switch (record.crawl_dates_kind?.["*"]) {
    case "crawl":
      return `a crawl run ${from} to ${to}`;
    case "scholar_query_dates": // local wall time: the offset wasn't recorded (TASK-077)
      return `Scholar searches run ${from} to ${to} (local time)`;
    case "scholar_query_dates_utc":
      return `Scholar searches run ${from} to ${to} (UTC)`;
    case "mixed":
      return `crawls and Scholar searches run ${from} to ${to} (Scholar dates in local time)`;
    case "mixed_utc":
      return `crawls and Scholar searches run ${from} to ${to} (UTC)`;
    default:
      // a kind this code doesn't know, or a v1 record (not recorded): the dates, and no claim about them
      return `records collected ${from} to ${to}`;
  }
}

/**
 * The caution shown instead of the methods text (copy RC-11, the CLI's wording; spec 05 §Pages), or `null`
 * when the record is citable (`identification_citable` is exactly `true`).
 */
export function citabilityCaution(record: SearchRecord): string | null {
  if (record.identification_citable === true) return null;
  if (record.identification_citable === false) {
    return (
      `bootstrap corpus (sources: ${(record.sources ?? []).join(", ")}): these counts describe that corpus, ` +
      "not a database; they are not PRISMA identification numbers"
    );
  }
  return (
    "not recorded whether this index is a bootstrap corpus: these counts may not be PRISMA identification " +
    "numbers"
  );
}

/** The record's default clauses and the limits its reader wrote, as the canonical query writes them. */
export interface Clauses {
  readonly defaults: readonly string[];
  readonly limits: readonly string[];
}

const FIELDS = ["venue", "year", "track", "status"] as const;

function slice(text: string, span: readonly number[]): string | null {
  const [start, end] = span;
  if (span.length !== 2 || start === undefined || end === undefined || start >= end) return null;
  try {
    const [a, b] = codePointSpanToUtf16(text, [start, end]);
    return text.slice(a, b);
  } catch {
    return null;
  }
}

/**
 * The default and limit clauses of `record.canonical`, from `/parse`'s report of that same string (design
 * §API fields needed): a field in `defaults` is a default clause; any other field with a clause of its own is
 * a limit the reader wrote, and one written more than once (or mixed with another field) is each clause
 * behind it. A filter nested inside an OR or NOT isn't a limit on the set: the string states it. `null` when
 * the report can't be trusted for this record: none, for another string, with errors, or read under another
 * `query_version` than the record's (the rules that separate the clauses may have changed).
 */
export function clausesOf(record: SearchRecord, parse: ParseResponse | null): Clauses | null {
  if (parse === null || parse.filters === null || parse.errors.length > 0) return null;
  if (parse.canonical !== record.canonical || parse.query_version !== record.query_version) return null;
  const { canonical } = record;
  const defaults: [number, string][] = [];
  const limits: [number, string][] = [];
  for (const field of FIELDS) {
    const clause = parse.filters[field];
    const spans =
      clause.span !== null
        ? [clause.span]
        : clause.reason === "multiple_clauses" || clause.reason === "mixed_fields"
          ? clause.blocking_spans
          : [];
    for (const span of spans) {
      const text = slice(canonical, span);
      if (text === null) continue;
      const into = parse.defaults.includes(field) ? defaults : limits;
      if (!into.some(([, t]) => t === text)) into.push([span[0] ?? 0, text]);
    }
  }
  const inOrder = (xs: [number, string][]) => xs.sort((a, b) => a[0] - b[0]).map(([, t]) => t);
  return { defaults: inOrder(defaults), limits: inOrder(limits) };
}

/** What each recorded translation code says in the methods text (spec 05 §Components 8), in the spec's order. */
export const TRANSLATION_CLAUSES: Readonly<Record<string, string>> = {
  COMPAT_SOURCE_ALIAS: "`source:` values became `venue:` filters",
  COMPAT_POP_PHRASE:
    "unquoted multi-word `|` items were read as phrases (openproceedings decision-002), unlike Google Scholar",
  COMPAT_POP_DOLLAR: "`$` was read as the Web of Science zero-or-one wildcard",
  COMPAT_NO_STEMMING: "openproceedings does not stem (terms listed in the record)",
};

function translationSentence(record: SearchRecord): string {
  const recorded = [...new Set(record.translations.map((t) => t.code))];
  const known = Object.keys(TRANSLATION_CLAUSES).filter((c) => recorded.includes(c));
  // a code this version doesn't word: its own recorded message, so nothing recorded is left out
  const other = recorded
    .filter((c) => !(c in TRANSLATION_CLAUSES))
    .map((c) => record.translations.find((t) => t.code === c)?.message ?? c);
  const clauses = [...known.map((c) => TRANSLATION_CLAUSES[c] ?? c), ...other];
  if (clauses.length === 0)
    return "The string was entered in Google Scholar syntax; no translation was recorded.";
  return `The string was entered in Google Scholar syntax and translated as recorded: ${clauses.join("; ")}.`;
}

function andList(items: readonly string[]): string {
  if (items.length <= 1) return items.join("");
  return `${items.slice(0, -1).join(", ")} and ${items[items.length - 1] ?? ""}`;
}

/** The removed buckets, itemised in the API's order (track, then status), `unknown` apart. Zeros are left out. */
export function removedBuckets(record: SearchRecord): string[] {
  const out: string[] = [];
  for (const map of [record.excluded.track, record.excluded.status]) {
    for (const [value, n] of Object.entries(map)) {
      if (value !== "unknown" && n > 0) out.push(`${num(n)} ${value}`);
    }
  }
  return out;
}

export interface MethodsInput {
  readonly record: SearchRecord;
  /** `POST /parse` of `record.canonical` (the default and limit clauses), or `null` when there is none. */
  readonly parseCanonical: ParseResponse | null;
  /**
   * `POST /parse` of `record.identification_query`: `PARSE_ALL_NEGATIVE` among its errors means the string
   * can't be cited as a search on its own (prisma-reporting). `null` when there is none.
   */
  readonly parseIdentification: ParseResponse | null;
  /** The record page's full URL. */
  readonly url: string;
}

/** Whether `/parse` said the identification string is all-negative (read under the record's query version). */
export function allNegative(record: SearchRecord, parse: ParseResponse | null): boolean {
  return (
    parse !== null &&
    parse.query_version === record.query_version &&
    parse.errors.some((e) => e.code === "PARSE_ALL_NEGATIVE")
  );
}

/** The methods text (spec 05 §Components 8). */
export function methodsText({ record, parseCanonical, parseIdentification, url }: MethodsInput): string {
  const clauses = clausesOf(record, parseCanonical);
  const window = builtFrom(record);
  const idq = record.identification_query;
  const identified = count(record.identified_total, "record", "records");

  const limits =
    clauses === null
      ? "within any limits it states"
      : clauses.limits.length === 0
        ? "with no limits"
        : `within the limits it states (${clauses.limits.map(code).join(", ")})`;

  let searched: string;
  if (idq === "") {
    searched = `with no search string (all indexed records), which identified ${identified} ${limits}.`;
  } else if (allNegative(record, parseIdentification)) {
    searched =
      `with the string ${code(record.canonical)}, which without its default filters identified ` +
      `${identified} ${limits}.`;
  } else {
    searched = `with the string ${code(idq)}, which identified ${identified} ${limits}.`;
  }
  const sentences = [
    `We searched openproceedings on ${utcDate(record.searched_at)} (index ${code(record.index_version)}` +
      `${window === null ? "" : `, built from ${window}`}) ${searched}`,
  ];

  if (record.mode === "scholar") {
    sentences.push(`The input as typed was ${code(record.input)}.`, translationSentence(record));
  } else if (idq !== "" && record.input !== idq) {
    sentences.push(`The input as typed was ${code(record.input)}.`);
  }

  const removed = record.excluded.total;
  const buckets = removedBuckets(record);
  const itemised = buckets.length === 0 ? "" : ` (${buckets.join(", ")})`;
  const unclassified =
    `that count includes ${count(record.unclassified_total, "unclassified record", "unclassified records")} ` +
    "(track or status unknown), itemised separately.";
  if (clauses !== null && clauses.defaults.length === 0 && removed === 0) {
    sentences.push("No default filter applied, so no records were removed before screening.");
  } else {
    const filters =
      clauses === null
        ? `The default filters (written out in the canonical query ${code(record.canonical)})`
        : clauses.defaults.length === 0
          ? "The default filters"
          : `Default ${clauses.defaults.length === 1 ? "filter" : "filters"} ${andList(clauses.defaults.map(code))}`;
    sentences.push(`${filters} removed ${num(removed)} of them before screening${itemised}; ${unclassified}`);
  }

  sentences.push(
    "Cross-source duplicates were merged at ingest, before indexing (merge counts, and look-alike pairs kept " +
      "apart by track or venue-year, are in the search record).",
    `Database scope: coverage report for snapshot ${code(record.snapshot_hash)}.`,
    `${count(record.total, "record was", "records were")} screened.`,
    `Search record: ${url}.`,
  );
  return sentences.join(" ");
}
