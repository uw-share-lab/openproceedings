/**
 * What a record's replay says (spec 05 §Pages `/record/[id]`; spec 04 §Search records; design R1–R4; copy
 * RC-2–RC-7, RC-3a). Pure: every count is the replay's or the record's as the API sent it. Strings hold query
 * text and codes in backticks (drawn by `Coded`); every value the API sent that a string quotes, in backticks or
 * bare (`refused`, the index and query versions), goes through `clip`, since a stored record or an index
 * manifest could hold a backtick, a newline or a bidi character (TASK-160).
 *
 * Statuses: `reproduced`; `drifted` with its changed inputs and `+added / −removed` ("membership-identical" on
 * `+0 / −0`); `drifted` that could not be re-run (`refused`: counts null, never "membership-identical");
 * withheld (`refused` is `API_TOO_MANY_VERIFIED_CLAUSES` or `API_QUERY_TOO_COSTLY`: this instance won't run
 * it); and `mismatch`, the blocking "do not cite" state.
 */
import { clip } from "./clip";
import type { RecordResponse, SearchRecord } from "./methods-text";
import { utcDate } from "./methods-text";

export type Replay = NonNullable<RecordResponse["replay"]>;
type Excluded = SearchRecord["excluded"];

const plural = (n: number, word: string) => `${n.toLocaleString("en-US")} ${word}${n === 1 ? "" : "s"}`;
const num = (n: number) => n.toLocaleString("en-US");

export const WITHHELD = ["API_TOO_MANY_VERIFIED_CLAUSES", "API_QUERY_TOO_COSTLY"] as const;

/** RC-3's "What changed" words per input; an input this version doesn't know gets none. */
export const CHANGE_MEANING: Readonly<Record<string, string>> = {
  snapshot_hash: "the corpus (papers added or re-crawled)",
  tokenizer_version: "how text is split into words",
  schema_version: "the index layout",
  ranking_params: "ranking only: never which papers match",
  query_version: "the query rules",
};

export interface ChangeRow {
  readonly input: string;
  readonly recorded: string;
  readonly current: string;
  readonly meaning: string;
}

export type ReplayView =
  | { readonly kind: "reproduced"; readonly text: string }
  | { readonly kind: "mismatch" }
  /** RC-5: the canonical no longer runs here. */
  | { readonly kind: "refused"; readonly text: string }
  /** RC-6: this instance won't run it (its limits are below what the record's query needs). */
  | { readonly kind: "withheld"; readonly text: string }
  | {
      readonly kind: "drifted";
      readonly text: string;
      /** RC-4, on `+0 / −0`. */
      readonly membershipIdentical: string | null;
      readonly changes: readonly ChangeRow[];
      /** RC-3a. */
      readonly exclusions: string;
      readonly cite: string;
      readonly added: number;
      readonly removed: number;
    };

function valueText(v: unknown): string {
  return typeof v === "string" ? v : JSON.stringify(v);
}

/** The removed buckets of `excluded`, itemised (track, then status; `unknown` named by its map), zeros left out. */
export function bucketsText(excluded: Excluded): string {
  const items: string[] = [];
  for (const [field, map] of [
    ["track", excluded.track],
    ["status", excluded.status],
  ] as const) {
    for (const [value, n] of Object.entries(map)) {
      if (n > 0) items.push(`${num(n)} ${value === "unknown" ? `${field} unknown` : value}`);
    }
  }
  return items.length === 0 ? "none" : items.join(" · ");
}

/** `today` is the UTC date the page was shown (RC-2's "Reproduced on <today>"). */
export function replayView(record: SearchRecord, replay: Replay, today: string): ReplayView {
  if (replay.status === "mismatch") return { kind: "mismatch" };
  if (replay.status === "reproduced") {
    return {
      kind: "reproduced",
      text:
        `Reproduced on ${today}: the same index and query version give the same ${plural(record.total, "paper")} ` +
        "and the same exclusions.",
    };
  }
  if (replay.refused === "API_TOO_MANY_VERIFIED_CLAUSES") {
    return {
      kind: "withheld",
      text:
        "Could not be re-run: `API_TOO_MANY_VERIFIED_CLAUSES` — this instance's limit is below the record's " +
        `${replay.verified_clauses === null ? "" : `${num(replay.verified_clauses)} `}position-verified clauses. ` +
        "The record and its exports are unchanged.",
    };
  }
  if (replay.refused === "API_QUERY_TOO_COSTLY") {
    return {
      kind: "withheld",
      text:
        "Could not be re-run: `API_QUERY_TOO_COSTLY` — its position checks would read more documents than this " +
        "instance allows in one query. The record and its exports are unchanged.",
    };
  }
  if (replay.refused !== null || replay.total === null) {
    return {
      kind: "refused",
      text: `Drifted — could not be re-run: \`${replay.refused === null ? "unknown" : clip(replay.refused)}\`. No counts were compared.`,
    };
  }
  const added = replay.added_total ?? 0;
  const removed = replay.removed_total ?? 0;
  const tally = `+${num(added)} / −${num(removed)}`;
  const onlyRules =
    replay.index_version === record.index_version && replay.changed.every((c) => c.input === "query_version");
  const text = onlyRules
    ? `Drifted: the query rules changed (query version ${clip(record.query_version)} → ${clip(replay.query_version)}). ` +
      `Re-run on the record's own index, it finds ${plural(replay.total, "paper")}: ${tally} against the record.`
    : `Drifted: this instance no longer has index \`${clip(record.index_version)}\`, so the search was re-run on ` +
      `index \`${clip(replay.index_version)}\`. It now finds ${plural(replay.total, "paper")}: ${tally} against the record.`;
  const exclusions =
    replay.excluded_match === false && replay.excluded !== null
      ? `Removed before screening on re-run: ${bucketsText(replay.excluded)} (recorded: ${bucketsText(record.excluded)})`
      : "Removed before screening on re-run: same exclusions";
  return {
    kind: "drifted",
    text,
    membershipIdentical:
      replay.membership_identical === true
        ? "+0 / −0: the re-run finds exactly the recorded papers (membership-identical), though the index or " +
          "query version changed."
        : null,
    changes: replay.changed.map((c) => ({
      input: c.input,
      recorded: valueText(c.recorded),
      current: valueText(c.current),
      meaning: CHANGE_MEANING[c.input] ?? "",
    })),
    exclusions,
    cite: `Cite the recorded counts below; they describe the search as it was run on ${utcDate(record.searched_at)}.`,
    added,
    removed,
  };
}

/** The saved panel's status line (SV-4; any other status uses the record page's line). */
export function savedLine(record: SearchRecord, replay: Replay, today: string): string | null {
  const view = replayView(record, replay, today);
  if (view.kind === "reproduced") return `Reproduced just now on index \`${clip(replay.index_version)}\`.`;
  if (view.kind === "mismatch") return null;
  return view.text;
}

/** The record's own exports are off when its index isn't the one the replay could use (design R5). */
export function indexGone(record: SearchRecord, replay: Replay | null): boolean {
  return replay !== null && replay.index_version !== record.index_version;
}
