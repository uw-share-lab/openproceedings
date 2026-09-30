/**
 * Exports (spec 04 §Exports; spec 05 §Components 7; design E1–E4, R1, R5; copy EX-E1–E7, RC-13). An export
 * is `GET /export`, pinned so it can only hand over the set that was shown: from a search, `q` + `mode` +
 * the shown `index_version` (a hot swap is then 409 `API_INDEX_VERSION_UNAVAILABLE`, never another set); from
 * a record, `record_id` alone (the record's stored ids, from its own index; never a re-run of `q`).
 *
 * The response headers are read **before** the body (design E1): `X-Index-Version` must be the shown index and
 * `X-Total` the shown total, or the body is abandoned and nothing is saved. A different index is "the index
 * changed" (E3); the same index with another count is a bug (EX-E3b; guarantee 4), never worded as a swap.
 * `X-Abstract-Source: unavailable` still downloads (the cited set is complete), but the file has no abstracts
 * (decision-021), so the result says so and the menu warns (EX-E8).
 */
import type { Api } from "@/api/client";
import { outcomeOf, type Failure } from "@/api/outcome";
import defaultsGolden from "@/help/syntax-golden.json";
import type { Mode, ParsedFilters } from "@/lib/search-state";

export const FORMATS = [
  { format: "ris", label: "RIS", description: "for Covidence, Zotero, EndNote" },
  { format: "csv", label: "CSV", description: "spreadsheet, UTF-8" },
  { format: "bibtex", label: "BibTeX", description: null },
  { format: "jsonl", label: "JSONL", description: "every field, one line each" },
] as const;

export type ExportFormat = (typeof FORMATS)[number]["format"];

const EXTENSIONS: Record<ExportFormat, string> = { ris: "ris", csv: "csv", bibtex: "bib", jsonl: "jsonl" };

/** What an export is pinned to, and what the reader was shown (the headers must agree with it). */
export type ExportSource =
  | {
      readonly kind: "search";
      readonly q: string;
      readonly mode: Mode;
      readonly indexVersion: string;
      readonly total: number;
    }
  | {
      readonly kind: "record";
      readonly recordId: string;
      readonly indexVersion: string;
      readonly total: number;
    };

export type ExportResult =
  | {
      readonly kind: "ok";
      readonly blob: Blob;
      readonly filename: string;
      /** `X-Abstract-Source: unavailable`: every abstract withheld, each record says why (decision-021). */
      readonly abstractsWithheld: boolean;
    }
  /** `X-Index-Version` isn't the shown index (EX-E4). */
  | { readonly kind: "index_changed"; readonly shown: string; readonly got: string }
  /** 409 `API_INDEX_VERSION_UNAVAILABLE`: the pinned index isn't served here (EX-E4's 409 line, RC-13). */
  | { readonly kind: "index_unavailable"; readonly shown: string }
  /** The same index, another count: guarantee 4 broken (EX-E3b). */
  | { readonly kind: "total_differs"; readonly shown: number; readonly got: number | null }
  | Failure;

/** `attachment; filename="openproceedings-….ris"` → the file name; a fallback when the header is absent. */
export function filenameOf(header: string | null, source: ExportSource, format: ExportFormat): string {
  const m = header === null ? null : /filename="([^"/\\]+)"/.exec(header);
  return m?.[1] ?? `openproceedings-${source.indexVersion}.${EXTENSIONS[format]}`;
}

export async function fetchExport(
  api: Api,
  source: ExportSource,
  format: ExportFormat,
  signal?: AbortSignal,
): Promise<ExportResult> {
  const query =
    source.kind === "search"
      ? { format, q: source.q, mode: source.mode, index_version: source.indexVersion }
      : { format, record_id: source.recordId };
  const outcome = await outcomeOf<Response>(async () => {
    const r = await api.GET("/api/v1/export", {
      params: { query },
      parseAs: "stream", // headers first: the body is read only once they match (design E1)
      ...(signal === undefined ? {} : { signal }),
    });
    return r.error === undefined
      ? { data: r.response, response: r.response }
      : { error: r.error, response: r.response };
  }, signal);
  if (outcome.kind !== "ok") {
    if (outcome.kind === "refused" && outcome.error.code === "API_INDEX_VERSION_UNAVAILABLE") {
      return { kind: "index_unavailable", shown: source.indexVersion };
    }
    return outcome;
  }
  const response = outcome.data;
  const abandon = () => void response.body?.cancel().catch(() => {});
  const version = response.headers.get("X-Index-Version");
  if (version !== source.indexVersion) {
    abandon();
    return { kind: "index_changed", shown: source.indexVersion, got: version ?? "(not sent)" };
  }
  const rawTotal = response.headers.get("X-Total");
  const total = rawTotal !== null && /^[0-9]+$/.test(rawTotal) ? Number(rawTotal) : null;
  if (total !== source.total) {
    abandon();
    return { kind: "total_differs", shown: source.total, got: total };
  }
  const blob = await response.blob();
  return {
    kind: "ok",
    blob,
    filename: filenameOf(response.headers.get("Content-Disposition"), source, format),
    abstractsWithheld: response.headers.get("X-Abstract-Source") === "unavailable",
  };
}

/** Hand a downloaded file to the browser under `filename` (an `<a download>` over an object URL). */
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.rel = "noopener";
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

/** The default track values (the backend's own, from the syntax golden it generates). */
export const DEFAULT_TRACKS: readonly string[] =
  defaultsGolden.defaults.find((d) => d.field === "track")?.values ?? [];
/** The default status values (`accepted`). */
export const DEFAULT_STATUSES: readonly string[] =
  defaultsGolden.defaults.find((d) => d.field === "status")?.values ?? [];

/**
 * The export menu's status or track warning (design E2; copy EX-E3, EX-E3a): the values the searched `q`'s
 * clause admits beyond the default, each with its facet count (exact: a facet is counted with every other
 * filter applied), listed, never summed, zeros left out; or, when the clause can't be read as one value list
 * (negated, nested, written more than once), the reason, with no numbers.
 */
export type FieldWarning =
  | { readonly field: "status" | "track"; readonly counts: readonly (readonly [string, number])[] }
  | { readonly field: "status" | "track"; readonly reason: string };

const REASON_WORDS: Readonly<Record<string, string>> = {
  negated: "negated",
  nested: "nested",
  multiple_clauses: "written more than once",
  mixed_fields: "nested",
};

export function fieldWarning(
  field: "status" | "track",
  filters: ParsedFilters,
  defaults: readonly string[],
  facets: Readonly<Record<string, number>>,
): FieldWarning | null {
  if (defaults.includes(field)) return null; // the default applies: accepted, main-track papers only
  const clause = filters[field];
  const usual = field === "status" ? DEFAULT_STATUSES : DEFAULT_TRACKS;
  if (clause.negated || clause.values === null) {
    const why = clause.negated ? "negated" : (REASON_WORDS[clause.reason ?? ""] ?? "nested");
    return { field, reason: why };
  }
  const counts = clause.values
    .filter((v) => !usual.includes(v))
    .map((v) => [v, facets[v] ?? 0] as const)
    .filter(([, n]) => n > 0);
  return counts.length === 0 ? null : { field, counts };
}

const listed = (counts: readonly (readonly [string, number])[]) =>
  counts.map(([v, n]) => `${n.toLocaleString("en-US")} ${v}`).join(", ");

/** The warning in the open menu (EX-E3, EX-E3a). */
export function warningText(w: FieldWarning): string {
  if (w.field === "status") {
    const tail =
      "Covidence doesn't show a paper's status to screeners (no keywords or notes on the screening card), so " +
      "they can't be told apart there. To screen accepted papers only, keep the default status filter.";
    return "counts" in w
      ? `This export includes papers that were not accepted: ${listed(w.counts)}. ${tail}`
      : `This export may include papers that were not accepted (the query's \`status:\` clause is ${w.reason}). ${tail}`;
  }
  const tail =
    "Covidence doesn't show a paper's track to screeners, so they can't be told apart there. To screen " +
    "main-track papers only, keep the default track filter.";
  return "counts" in w
    ? `This export includes ${listed(w.counts)} papers. ${tail}`
    : `This export may include papers outside the default tracks (the query's \`track:\` clause is ${w.reason}). ${tail}`;
}

/** The one line beside the closed Export button (EX-E3 closed-menu line). */
export function warningLine(w: FieldWarning): string {
  if ("counts" in w) return `Includes ${listed(w.counts)} papers`;
  return w.field === "status"
    ? "May include papers that were not accepted"
    : "May include papers outside the default tracks";
}

/** EX-E7, the "Importing into Covidence" disclosure. */
export const COVIDENCE_TEXT =
  "Import the RIS file into *Title and abstract screening*. Covidence shows screeners the title, abstract, " +
  "authors, year, source and DOI, but not a paper's keywords, notes or links, so its status (accepted, " +
  "rejected, …) and track can't be seen while screening: choose what screeners get with this search's filters " +
  "before exporting. Each record's Notes line names this search (index, query hash, export date), and so do the " +
  "CSV and JSONL columns, so any paper in your Covidence library can be traced back. Covidence merges this " +
  "export's papers with copies from other databases, but not with a copy dated a different year (for example a " +
  "preprint); check its duplicate list for those. Report the duplicates Covidence removes in PRISMA's " +
  "*duplicates removed* box; they are separate from openproceedings' own merges, which the search record " +
  "describes.";
