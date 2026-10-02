import { describe, expect, it } from "vitest";
import { HOSTILE, quotedSafely } from "@/test/hostile";
import { copy, RECORDS } from "@/test/record-fixture";
import { bucketsText, indexGone, replayView, savedLine, type Replay } from "./replay-status";

const C = RECORDS.limits;
const record = C.replayed.record;
const replay = (over: Partial<Replay> = {}): Replay => {
  const r = copy(C.replayed.replay);
  if (r === null) throw new Error("the fixture's replay is null");
  return { ...r, ...over };
};

describe("replayView and savedLine (copy RC-2–RC-7, SV-4)", () => {
  it("reads the API's own reproduced replay", () => {
    expect(replayView(record, replay(), "2026-09-27")).toEqual({
      kind: "reproduced",
      text: `Reproduced on 2026-09-27: the same index and query version give the same ${record.total} papers and the same exclusions.`,
    });
    expect(savedLine(record, replay(), "2026-09-27")).toBe(
      `Reproduced just now on index \`${record.index_version}\`.`,
    );
  });

  it("gives mismatch no line of its own (the blocking state is drawn apart)", () => {
    expect(replayView(record, replay({ status: "mismatch" }), "x")).toEqual({ kind: "mismatch" });
    expect(savedLine(record, replay({ status: "mismatch" }), "x")).toBeNull();
  });

  it("words API_QUERY_TOO_COSTLY as withheld, never as reproduced or a drift with no reason", () => {
    const v = replayView(
      record,
      replay({
        status: "drifted",
        refused: "API_QUERY_TOO_COSTLY",
        total: null,
        added_total: null,
        removed_total: null,
      }),
      "x",
    );
    expect(v).toEqual({
      kind: "withheld",
      text:
        "Could not be re-run: `API_QUERY_TOO_COSTLY` — its position checks would read more documents than this " +
        "instance allows in one query. The record and its exports are unchanged.",
    });
  });

  it("names an input it doesn't know without a meaning", () => {
    const v = replayView(
      record,
      replay({
        status: "drifted",
        index_version: "other",
        changed: [
          { input: "future_input" as "snapshot_hash", kind: "method", recorded: { a: 1 }, current: 2 },
        ],
      }),
      "x",
    );
    expect(v.kind === "drifted" && v.changes).toEqual([
      { input: "future_input", recorded: '{"a":1}', current: "2", meaning: "" },
    ]);
  });

  it("itemises buckets with unknown named by its map, zeros left out", () => {
    expect(bucketsText(record.excluded)).toBe(
      [
        ...Object.entries(record.excluded.track).map(
          ([v, n]) => [v === "unknown" ? "track unknown" : v, n] as const,
        ),
        ...Object.entries(record.excluded.status).map(
          ([v, n]) => [v === "unknown" ? "status unknown" : v, n] as const,
        ),
      ]
        .filter(([, n]) => n > 0)
        .map(([v, n]) => `${n} ${v}`)
        .join(" · "),
    );
    expect(bucketsText({ total: 0, track: { unknown: 0 }, status: {} })).toBe("none");
  });

  it("calls the record's index gone only when a replay ran elsewhere", () => {
    expect(indexGone(record, null)).toBe(false);
    expect(indexGone(record, replay())).toBe(false);
    expect(indexGone(record, replay({ index_version: "other" }))).toBe(true);
  });
});

describe("values the API sent are clipped wherever a line quotes them (TASK-160)", () => {
  it.each(HOSTILE)("a refusal code %j is quoted as %j", (code, shown) => {
    const v = replayView(
      record,
      replay({
        status: "drifted",
        refused: code as Replay["refused"],
        total: null,
        added_total: null,
        removed_total: null,
      }),
      "x",
    );
    expect(v).toEqual({
      kind: "refused",
      text: `Drifted — could not be re-run: \`${shown}\`. No counts were compared.`,
    });
    if (v.kind === "refused") quotedSafely(v.text);
  });

  it.each(HOSTILE)("both index versions %j are quoted as %j", (version, shown) => {
    const r = replay({
      status: "drifted",
      index_version: `${version}-now`,
      total: 3,
      added_total: 1,
      removed_total: 0,
    });
    const v = replayView({ ...record, index_version: version }, r, "x");
    expect(v.kind === "drifted" && v.text).toBe(
      `Drifted: this instance no longer has index \`${shown}\`, so the search was re-run on index ` +
        `\`${shown}-now\`. It now finds 3 papers: +1 / −0 against the record.`,
    );
    if (v.kind === "drifted") quotedSafely(v.text);
  });

  it.each(HOSTILE)("both query versions %j are quoted bare as %j", (version, shown) => {
    const r = replay({
      status: "drifted",
      query_version: `${version}2`,
      changed: [{ input: "query_version", kind: "method", recorded: version, current: `${version}2` }],
    });
    const v = replayView({ ...record, query_version: version }, r, "x");
    expect(
      v.kind === "drifted" &&
        v.text.startsWith(
          `Drifted: the query rules changed (query version ${shown} → ${shown}2). Re-run on the record's own index`,
        ),
    ).toBe(true);
    if (v.kind === "drifted") quotedSafely(v.text);
  });

  it.each(HOSTILE)("the saved panel quotes the index version %j as %j", (version, shown) => {
    const line = savedLine({ ...record, index_version: version }, replay({ index_version: version }), "x");
    expect(line).toBe(`Reproduced just now on index \`${shown}\`.`);
    quotedSafely(line ?? "");
  });
});
