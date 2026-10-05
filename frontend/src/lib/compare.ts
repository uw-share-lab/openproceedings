/**
 * Comparing a search with a reviewer's own RIS file (spec 04 §Comparing with a RIS file; spec 05 §Components
 * 9; TASK-177): `POST /compare` with the file as the body, and the words for what it answers.
 *
 * The server decides everything: which records match the index, which list each paper is in, why, and every
 * count (`*_total`, `reason_totals`). Nothing here matches, counts or builds a CSV cell: the lists' files are
 * the response's own text (`csv`, `added_ris`), saved as sent. The file is sent as its bytes, never decoded in
 * the browser (a decode would replace what isn't UTF-8 silently, and the server could no longer refuse it).
 */
import type { MethodResponse } from "openapi-fetch";
import type { Api, Schemas } from "@/api/client";
import { outcomeOf, type Outcome } from "@/api/outcome";
import type { Mode } from "@/lib/search-state";

export const RIS_MEDIA = "application/x-research-info-systems";

/** `/compare`'s 200 body as the typed client returns it. */
export type Comparison = MethodResponse<Api, "post", "/api/v1/compare">;
export type CompareRow = Comparison["kept"][number];
export type NotComparedRow = Comparison["not_compared"][number];
export type CompareLimits = NonNullable<Schemas["Limits"]["compare"]>;

/** The four lists of papers, in the order the summary shows them. */
export const LISTS = ["kept", "dropped", "not_in_index", "added"] as const;
export type ListName = (typeof LISTS)[number];

export const LIST_LABELS: Record<ListName | "not_compared", string> = {
  kept: "Kept",
  dropped: "Dropped",
  not_in_index: "Not in the index",
  added: "Added",
  not_compared: "Not compared",
};

/** "1,756 dropped papers", "8 papers not in the index": a list's count with its noun (copy CM-6). */
export function listCount(list: ListName, count: number): string {
  const papers = count === 1 ? "paper" : "papers";
  const shown = count.toLocaleString("en-US");
  if (list === "not_in_index") return `${shown} ${papers} not in the index`;
  return `${shown} ${list} ${papers}`;
}

/** What each list means, in one line (the summary table's second column; copy CM-4). */
export const LIST_MEANINGS: Record<ListName, string> = {
  kept: "in your file and in this search's results",
  dropped: "in your file and in the index, but not in this search's results",
  not_in_index: "in your file; the index has no record of them, so the search can't find them",
  added: "in this search's results, not in your file",
};

export async function postCompare(
  api: Api,
  search: { readonly q: string; readonly mode: Mode },
  file: Blob,
  signal?: AbortSignal,
): Promise<Outcome<Comparison>> {
  return outcomeOf(
    () =>
      api.POST("/api/v1/compare", {
        params: { query: { q: search.q, mode: search.mode } },
        // The schema types a binary body as a string. What is sent is the file itself, byte for byte.
        body: "",
        bodySerializer: () => file,
        headers: { "Content-Type": RIS_MEDIA },
        ...(signal === undefined ? {} : { signal }),
      }),
    signal,
  );
}

/**
 * A size to one decimal in binary megabytes, as the caps are (`3.5 MB`), or in kilobytes when it is under a
 * tenth of one (`2.0 KB`): an instance's cap can be that small, and "0.0 MB" would say nothing.
 */
export function megabytes(bytes: number): string {
  const one = { minimumFractionDigits: 1, maximumFractionDigits: 1 };
  const mb = bytes / (1024 * 1024);
  if (mb < 0.1) return `${(bytes / 1024).toLocaleString("en-US", one)} KB`;
  return `${mb.toLocaleString("en-US", one)} MB`;
}

/**
 * Why this file can't be sent, or `null`: a convenience before the upload (the server's caps decide; a file
 * over `max_body_bytes` would be refused there with 413 before it is read).
 */
export function fileProblem(file: { readonly size: number }, limits: CompareLimits): string | null {
  if (file.size === 0) return "This file is empty. Choose a RIS export that holds records.";
  if (file.size > limits.max_body_bytes) {
    return (
      `This file is ${megabytes(file.size)}; this instance compares files up to ` +
      `${megabytes(limits.max_body_bytes)}. Export it without abstracts (only titles, venues, years and links ` +
      "are compared), or split it."
    );
  }
  return null;
}

/** The caps in one line (copy CM-3), from `/meta`'s `limits.compare`. */
export function limitsLine(limits: CompareLimits): string {
  return (
    `Up to ${megabytes(limits.max_body_bytes)} and ${limits.max_records.toLocaleString("en-US")} records, ` +
    "UTF-8 RIS (Publish or Perish, Zotero and EndNote export it)."
  );
}

const MATCHED_BY: Record<string, string> = {
  forum_id: "matched by its OpenReview link",
  proceedings_id: "matched by its proceedings link",
  title_venue_year: "matched by title, venue and year",
  not_found: "no record with this title in that venue and year, and no link to an indexed paper",
  ambiguous: "its link or title names several index records, so none was chosen",
  no_year: "it has no year, so only a link could match it",
  no_venue: "its venue is cut short or missing, so its title was not matched",
  truncated_title: "its title is cut short (…), so it can't be matched",
};

/** How a record of the file was matched, or why it wasn't (an unknown value is shown as sent: open enum). */
export function matchedByText(matchedBy: string | null): string {
  if (matchedBy === null) return "";
  return MATCHED_BY[matchedBy] ?? matchedBy;
}

const REASONS: Record<string, string> = {
  filtered: "excluded by a default filter",
  full_text: "no exact match in its title or abstract",
  stemming: "matches only as another word form",
  compat_reading: "matches only as Google Scholar reads the query",
  coverage_gap: "not in the index",
  unsettled: "can't be decided automatically",
  our_bug: "openproceedings judges it both ways (a bug: please report it)",
};
const ADDED_REASONS: Record<string, string> = {
  scholar_missed: "an exact match your file doesn't hold",
  compat_reading: "matches as this search reads the query, not as Google Scholar reads it",
  scholar_cap: "its venue and year hit Google Scholar's 1,000-result cap in your file",
  our_bug: "openproceedings judges it both ways (a bug: please report it)",
};

/** A `reason` in words for one list (an unknown value is shown as sent: the enum is open). */
export function reasonText(list: ListName, reason: string | null): string {
  if (reason === null) return "";
  return (list === "added" ? ADDED_REASONS[reason] : REASONS[reason]) ?? reason;
}

const NOT_COMPARED: Record<string, string> = {
  venue_unrecognised: "its venue is not NeurIPS, ICLR or ICML",
  venue: "it matched a record outside the compared venues",
  year: "it matched a record outside the compared years",
};

export function notComparedText(reason: string): string {
  return NOT_COMPARED[reason] ?? reason;
}

/** A reason as a count's sentence, [one paper, several]: "1 paper has …", "1,713 papers have …" (copy CM-7). */
const COUNTED: Record<string, readonly [string, string]> = {
  filtered: ["is excluded by a default filter", "are excluded by a default filter"],
  full_text: [
    "has no exact match in its title or abstract",
    "have no exact match in their title or abstract",
  ],
  stemming: ["matches only as another word form", "match only as another word form"],
  compat_reading: [
    "matches only as Google Scholar reads the query",
    "match only as Google Scholar reads the query",
  ],
  coverage_gap: ["is not in the index", "are not in the index"],
  unsettled: ["can't be decided automatically", "can't be decided automatically"],
  our_bug: [
    "is judged both ways by openproceedings (a bug: please report it)",
    "are judged both ways by openproceedings (a bug: please report it)",
  ],
};
const COUNTED_ADDED: Record<string, readonly [string, string]> = {
  scholar_missed: ["matches exactly and is not in your file", "match exactly and are not in your file"],
  compat_reading: [
    "matches as this search reads the query, not as Google Scholar reads it",
    "match as this search reads the query, not as Google Scholar reads it",
  ],
  scholar_cap: [
    "is from a venue and year that hit Google Scholar's 1,000-result cap in your file",
    "are from a venue and year that hit Google Scholar's 1,000-result cap in your file",
  ],
  our_bug: COUNTED.our_bug as readonly [string, string],
};

/**
 * What a reviewer can do about a paper with each reason (copy CM-19): a dropped or missing paper's count is
 * never left without a next step.
 */
const NEXT_STEP: Record<string, string> = {
  filtered: "to include such a paper, write its track or status into the query (its row says which)",
  full_text:
    "no form of this query finds such a paper by its title or abstract; keep it from your own file if it belongs in the review",
  stemming: "add $ to that word (the Add $ action under the query) to match its other forms",
  compat_reading:
    "write the query as Google Scholar reads it (its translation notice shows how) to match such a paper",
  coverage_gap: "keep such a paper from your own file: no query here can find it",
  unsettled: "check such a paper by hand (its row says what is undecided)",
  our_bug: "please report it with this query",
};

/**
 * "1,713 papers have no exact match in their title or abstract: no form of this query finds …": the server's
 * counts per reason, each a sentence of its own with what to do (an unknown reason is shown as sent).
 */
export function reasonLines(list: ListName, totals: Readonly<Record<string, number>>): string[] {
  return Object.entries(totals).map(([reason, n]) => {
    const words = (list === "added" ? COUNTED_ADDED : COUNTED)[reason];
    const papers = `${n.toLocaleString("en-US")} ${n === 1 ? "paper" : "papers"}`;
    if (words === undefined) return `${papers}: ${reason}.`;
    const next = list === "added" && reason !== "our_bug" ? undefined : NEXT_STEP[reason];
    return `${papers} ${n === 1 ? words[0] : words[1]}${next === undefined ? "" : `: ${next}`}.`;
  });
}

/**
 * What a person must decide about a row the automation couldn't settle (copy CM-20): named, never just
 * "needs a person".
 */
export function undecidedText(list: ListName, row: Pick<CompareRow, "reason" | "settled">): string {
  if (row.settled) return "";
  if (row.reason === "our_bug") return "to report: openproceedings judged it both ways";
  if (list === "not_in_index") return "to check: is it in the index under another title, venue or year?";
  if (list === "added") return "to check: is it the paper your file holds under another record?";
  return "to check: does the paper itself match the query? (its row says what is undecided)";
}

/** The start of a `not_in_index` row's `detail` that `matched_by` already says (copy USAB-N3). */
const UNMATCHED = "no forum id, proceedings id or title+venue+year match in the snapshot";

/** A row's evidence as shown: what `matched_by` already says is left out, the rest (links, near titles) kept. */
export function detailText(list: ListName, row: Pick<CompareRow, "detail">): string {
  if (list !== "not_in_index" || !row.detail.startsWith(UNMATCHED)) return row.detail;
  return row.detail.slice(UNMATCHED.length).replace(/^;\s*/, "");
}

/**
 * One sentence that says what the comparison found and on what, to paste into notes (copy CM-21; the server
 * keeps nothing of it: a place in the search record is TASK-195).
 */
export function summaryText(c: Comparison, fileName: string, date: string): string {
  const n = (x: number) => x.toLocaleString("en-US");
  return (
    `On ${date}, the query ${c.query.canonical} (canonical_hash ${c.query.canonical_hash}) on openproceedings ` +
    `index ${c.index_version}, compared with ${fileName} (${n(c.records_total)} records read, ` +
    `${n(c.papers_total)} papers compared): ${n(c.kept_total)} kept, ${n(c.dropped_total)} dropped, ` +
    `${n(c.not_in_index_total)} not in the index; it adds ${n(c.added_total)} papers the file doesn't hold.`
  );
}

const HEX = /^[0-9a-f]+$/;

/** `openproceedings-<index_version>-<hash12>-<list>.<ext>`: an export's name, with which list it is. */
export function downloadName(
  comparison: Pick<Comparison, "index_version" | "query">,
  list: ListName | "not_compared",
  ext: "csv" | "ris",
): string {
  const hash = comparison.query.canonical_hash.slice(0, 12);
  const version = HEX.test(comparison.index_version) ? comparison.index_version : "index";
  return `openproceedings-${version}-${HEX.test(hash) ? hash : "query"}-${list.replaceAll("_", "-")}.${ext}`;
}

/** The announcement when a comparison lands (copy CM-9). */
export function doneText(c: Comparison): string {
  const n = (x: number) => x.toLocaleString("en-US");
  return (
    `Comparison done: ${n(c.kept_total)} kept, ${n(c.dropped_total)} dropped, ` +
    `${n(c.not_in_index_total)} not in the index, ${n(c.added_total)} added.`
  );
}
