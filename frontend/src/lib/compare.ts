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
  doi: "matched by its DOI",
  title_venue_year: "matched by title, venue and year",
  not_found: "no record with this title in that venue and year, and no link or DOI naming an indexed paper",
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
  query_limit: "outside a limit your query writes (its year, venue, track or status)",
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

/**
 * A `not_in_index` row's `query_limit` (TASK-185) is judged on the file's own venue and year: the index holds no
 * record of the paper, so widening the limit can never find it, and its words and step are a coverage gap's.
 */
const NOT_IN_INDEX_LIMIT = {
  row: "not in the index; its year or venue in your file is outside a limit your query writes",
  counted: [
    "is not in the index, and its year or venue in your file is outside a limit your query writes",
    "are not in the index, and their year or venue in your file is outside a limit your query writes",
  ],
} as const;

/** A `reason` in words for one list (an unknown value is shown as sent: the enum is open). */
export function reasonText(list: ListName, reason: string | null): string {
  if (reason === null) return "";
  if (list === "not_in_index" && reason === "query_limit") return NOT_IN_INDEX_LIMIT.row;
  return (list === "added" ? ADDED_REASONS[reason] : REASONS[reason]) ?? reason;
}

const NOT_COMPARED: Record<string, string> = {
  // a venue string matching none of the indexed venues' names (Web of Science writes it with its volume), and no link
  // or DOI naming an indexed paper: it may well be an indexed venue's paper, so never "its venue is not …"
  venue_unrecognised:
    "its venue is not recognised as one of the indexed venues, and no link or DOI names an indexed paper",
  venue: "it matched a record outside the compared venues",
  year: "it matched a record outside the compared years",
};

export function notComparedText(reason: string): string {
  return NOT_COMPARED[reason] ?? reason;
}

/** A reason as a count's sentence, [one paper, several]: "1 paper has …", "1,713 papers have …" (copy CM-7). */
const COUNTED: Record<string, readonly [string, string]> = {
  query_limit: ["is outside a limit your query writes", "are outside a limit your query writes"],
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
 * never left without a next step. A word form's step names `*`, since such a form can be any number of letters
 * longer (`evaluated`, `evaluating`) and `$` adds only one; it depends on the mode only in naming the "Add $"
 * action under the query, Scholar mode's alone (USAB-R2-1, R3-2).
 */
const NEXT_STEP: Record<string, string> = {
  query_limit: "to include such a paper, widen that limit in the query (its row names the clause)",
  filtered: "to include such a paper, write its track or status into the query (its row says which)",
  full_text:
    "no form of this query finds such a paper by its title or abstract; keep it from your own file if it belongs in the review",
  stemming: "type * after its stem (e.g. evaluat*) to match its other forms; $ adds only one letter or digit",
  compat_reading:
    "write the query as Google Scholar reads it (its translation notice shows how) to match such a paper",
  coverage_gap: "Keep such a paper from your own file; no query here can find it",
  unsettled: "check such a paper by hand (its row says what is undecided)",
  our_bug: "please report it with this query",
};
const SCHOLAR_STEMMING_STEP =
  "type * after its stem (e.g. evaluat*) to match its other forms; $ adds only one letter or digit (the Add $ " +
  "action under the query)";

/**
 * "1,713 papers have no exact match in their title or abstract: no form of this query finds …": the server's
 * counts per reason, each a sentence of its own with what to do (an unknown reason is shown as sent).
 */
export function reasonLines(list: ListName, totals: Readonly<Record<string, number>>, mode: Mode): string[] {
  return Object.entries(totals).map(([reason, n]) => {
    const missing = list === "not_in_index" && reason === "query_limit";
    const words = missing ? NOT_IN_INDEX_LIMIT.counted : (list === "added" ? COUNTED_ADDED : COUNTED)[reason];
    const papers = `${n.toLocaleString("en-US")} ${n === 1 ? "paper" : "papers"}`;
    if (words === undefined) return `${papers}: ${reason}.`;
    const next =
      list === "added" && reason !== "our_bug"
        ? undefined
        : reason === "stemming" && mode === "scholar"
          ? SCHOLAR_STEMMING_STEP
          : NEXT_STEP[missing ? "coverage_gap" : reason];
    // a step that is a sentence of its own (a capital) follows a full stop, never a second colon (USAB-R2-N)
    const joint = next === undefined ? "" : /^[A-Z]/.test(next) ? `. ${next}` : `: ${next}`;
    return `${papers} ${n === 1 ? words[0] : words[1]}${joint}.`;
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
const UNMATCHED = "no forum id, proceedings id, DOI or title+venue+year match in the snapshot";

/** A row's evidence as shown: what `matched_by` already says is left out, the rest (links, near titles) kept. */
export function detailText(list: ListName, row: Pick<CompareRow, "detail">): string {
  if (list !== "not_in_index" || !row.detail.startsWith(UNMATCHED)) return row.detail;
  return row.detail.slice(UNMATCHED.length).replace(/^;\s*/, "");
}

/**
 * The file's sha256 as 64 hex digits, computed here from the bytes `postCompare` sends (the File the reviewer
 * chose), or `null` where this browser can't: Web Crypto exists only in a secure context (https, or
 * localhost), and a file that can't be read has no digest. The server is never asked for it (decision-043:
 * nothing of the file is echoed or kept beyond what decision-035 lists).
 */
export async function fileSha256(file: Blob): Promise<string | null> {
  const subtle = globalThis.crypto?.subtle;
  if (subtle === undefined) return null;
  try {
    const digest = await subtle.digest("SHA-256", new Uint8Array(await file.arrayBuffer()));
    return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
  } catch {
    return null;
  }
}

/**
 * The comparison as one citable sentence (copy CM-21; decision-043, prisma-reporting skill §Group counts and
 * `/compare`): a search-development aid, never a flow-diagram number, cited with the reviewer's own file (its
 * sha256), the UTC date it was run, the full `index_version` and the query's `canonical_hash`. The server
 * keeps nothing of it, and a search record never notes it (decision-043): the sentence is the citable form.
 */
export function summaryText(
  c: Comparison,
  file: { readonly name: string; readonly sha256: string | null },
  date: string,
): string {
  const n = (x: number) => x.toLocaleString("en-US");
  const count = (x: number, one: string) => `${n(x)} ${x === 1 ? one : `${one}s`}`;
  const hash =
    file.sha256 === null
      ? "sha256 not computed by this browser: compute it from your copy"
      : `sha256 \`${file.sha256}\``;
  // every record of the file accounted for (records_total = papers + not compared + repeats), so a reader can
  // see where a file's records went (a Web of Science file's unmatched records are mostly not compared);
  // repeats only when there are some
  const parts = [
    `${count(c.papers_total, "paper")} compared`,
    `${n(c.not_compared_total)} not compared (venue not recognised, or outside the indexed venues and years)`,
    ...(c.duplicates_total > 0 ? [`${count(c.duplicates_total, "repeat")} of a paper already counted`] : []),
  ];
  const accounted =
    parts.length === 2 ? parts.join(" and ") : `${parts.slice(0, -1).join(", ")}, and ${parts.at(-1) ?? ""}`;
  return (
    `As a search-development check (not a PRISMA flow-diagram count), on ${date} (UTC) we compared the RIS ` +
    `file ${file.name} (${hash}; ${count(c.records_total, "record")} read: ${accounted}) ` +
    `with the query \`${c.query.canonical}\` ` +
    `(canonical_hash \`${c.query.canonical_hash}\`) on openproceedings (index \`${c.index_version}\`): ` +
    `${n(c.kept_total)} kept, ${n(c.dropped_total)} dropped, ${n(c.not_in_index_total)} not in the index, ` +
    `and ${count(c.added_total, "paper")} added that the file doesn't hold.`
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
