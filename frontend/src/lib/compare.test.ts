import { describe, expect, it } from "vitest";
import { createApi } from "@/api/client";
import { json, stubFetch } from "@/test/api-stub";
import { COMPARE as fixture } from "@/test/compare-fixture";
import {
  doneText,
  downloadName,
  fileProblem,
  limitsLine,
  listCount,
  matchedByText,
  megabytes,
  notComparedText,
  postCompare,
  reasonsLine,
  reasonText,
  RIS_MEDIA,
  type CompareLimits,
} from "./compare";

const LIMITS: CompareLimits = {
  max_body_bytes: 16 * 1024 * 1024,
  max_records: 5000,
  max_line_length: 32768,
  max_title_length: 1000,
  max_results: 5000,
  max_seconds: 60,
  max_response_bytes: 16 * 1024 * 1024,
};

describe("postCompare", () => {
  it("sends the file's own bytes as a RIS body, with the query in the URL", async () => {
    const { fetch, calls } = stubFetch(() => json(fixture.response));
    const file = new Blob([fixture.file], { type: "text/plain" });
    const outcome = await postCompare(
      createApi("http://api.test", fetch),
      { q: "trust$", mode: "scholar" },
      file,
    );
    expect(outcome.kind).toBe("ok");
    const [call] = calls;
    expect(call?.method).toBe("POST");
    expect(call?.path).toBe("/api/v1/compare");
    expect([...(call?.query.entries() ?? [])]).toEqual([
      ["q", "trust$"],
      ["mode", "scholar"],
    ]);
    expect(call?.contentType).toBe(RIS_MEDIA); // the declared type is RIS whatever the browser guessed
    expect(call?.body).toBe(fixture.file);
  });

  it("gives a refusal as data, with its code and message", async () => {
    const { fetch } = stubFetch(() => json(fixture.invalid, 422));
    const outcome = await postCompare(
      createApi("http://api.test", fetch),
      { q: "a", mode: "native" },
      new Blob(["x"]),
    );
    expect(outcome).toMatchObject({ kind: "refused", status: 422, error: { code: "API_RIS_INVALID" } });
  });

  it("does not decode the file: bytes that aren't UTF-8 arrive as they are", async () => {
    const seen: number[][] = [];
    const fetchImpl: typeof globalThis.fetch = async (input) => {
      if (!(input instanceof Request)) throw new Error("the typed client always passes a Request");
      seen.push([...new Uint8Array(await input.arrayBuffer())]);
      return json(fixture.invalid, 422);
    };
    await postCompare(
      createApi("http://api.test", fetchImpl),
      { q: "a", mode: "native" },
      new Blob([new Uint8Array([0x54, 0xff, 0xfe, 0x59])]),
    );
    expect(seen).toEqual([[0x54, 0xff, 0xfe, 0x59]]);
  });
});

describe("the words", () => {
  it("names every reason the API documents, per list", () => {
    for (const reason of ["filtered", "full_text", "stemming", "compat_reading", "unsettled", "our_bug"]) {
      expect(reasonText("dropped", reason)).not.toBe(reason);
    }
    for (const reason of ["scholar_missed", "compat_reading", "scholar_cap", "our_bug"]) {
      expect(reasonText("added", reason)).not.toBe(reason);
    }
    expect(reasonText("dropped", "filtered")).toBe("excluded by a default filter"); // the glossary's word
    expect(reasonText("dropped", null)).toBe("");
  });

  it("shows a value it doesn't know as sent (the enums are open)", () => {
    expect(reasonText("dropped", "a_new_class")).toBe("a_new_class");
    expect(matchedByText("a_new_rule")).toBe("a_new_rule");
    expect(notComparedText("a_new_reason")).toBe("a_new_reason");
  });

  it("words how each record of the fixture was matched", () => {
    const rules = new Set(
      [...fixture.response.kept, ...fixture.response.not_in_index].map((r) => r.matched_by),
    );
    expect(rules.size).toBeGreaterThan(1);
    for (const rule of rules) expect(matchedByText(rule)).not.toBe(rule);
    expect(matchedByText(null)).toBe("");
  });

  it("writes each reason's count as a sentence, with the server's counts in the server's order", () => {
    expect(reasonsLine("dropped", fixture.response.reason_totals.dropped)).toBe(
      "2 papers are excluded by a default filter · 2 papers match only as another word form · " +
        "2 papers have no exact match in their title or abstract",
    );
    expect(reasonsLine("kept", fixture.response.reason_totals.kept)).toBe("");
    expect(reasonsLine("added", { scholar_missed: 154 })).toBe(
      "154 papers match exactly and are not in your file",
    );
    expect(reasonsLine("added", { scholar_missed: 1 })).toBe(
      "1 paper matches exactly and is not in your file",
    );
    expect(reasonsLine("dropped", { full_text: 1, unsettled: 41 })).toBe(
      "1 paper has no exact match in its title or abstract · 41 papers can't be decided automatically",
    );
    expect(reasonsLine("not_in_index", { coverage_gap: 3 })).toBe("3 papers are not in the index");
    expect(reasonsLine("dropped", { a_new_class: 2 })).toBe("2 papers: a_new_class"); // open enum
    // every reason the API documents has its sentence, in both lists it can appear in
    for (const reason of [
      "filtered",
      "full_text",
      "stemming",
      "compat_reading",
      "coverage_gap",
      "unsettled",
      "our_bug",
    ]) {
      expect(reasonsLine("dropped", { [reason]: 2 })).not.toContain(reason);
    }
    for (const reason of ["scholar_missed", "compat_reading", "scholar_cap", "our_bug"]) {
      expect(reasonsLine("added", { [reason]: 2 })).not.toContain(reason);
    }
  });

  it("counts a list with its noun", () => {
    expect(listCount("dropped", 1756)).toBe("1,756 dropped papers");
    expect(listCount("kept", 1)).toBe("1 kept paper");
    expect(listCount("not_in_index", 8)).toBe("8 papers not in the index");
    expect(listCount("not_in_index", 1)).toBe("1 paper not in the index");
    expect(listCount("added", 16)).toBe("16 added papers");
  });

  it("announces the four counts", () => {
    expect(doneText(fixture.response)).toBe(
      `Comparison done: ${fixture.response.kept_total} kept, ${fixture.response.dropped_total} dropped, ` +
        `${fixture.response.not_in_index_total} not in the index, ${fixture.response.added_total} added.`,
    );
  });
});

describe("the file", () => {
  it("is checked against the instance's cap before it is sent", () => {
    expect(fileProblem({ size: 0 }, LIMITS)).toMatch(/empty/);
    expect(fileProblem({ size: LIMITS.max_body_bytes }, LIMITS)).toBeNull();
    expect(fileProblem({ size: LIMITS.max_body_bytes + 1 }, LIMITS)).toBe(
      "This file is 16.0 MB; this server compares files up to 16.0 MB. Export it without abstracts (only " +
        "titles, venues, years and links are compared), or split it.",
    );
    expect(fileProblem({ size: 22_334_000 }, LIMITS)).toMatch(/^This file is 21\.3 MB/);
  });

  it("states the caps from /meta", () => {
    expect(megabytes(3_687_464)).toBe("3.5 MB");
    expect(megabytes(2_048)).toBe("2.0 KB"); // a small cap is never "0.0 MB"
    expect(megabytes(104_857)).toBe("102.4 KB");
    expect(megabytes(104_858)).toBe("0.1 MB");
    expect(fileProblem({ size: 3_000 }, { ...LIMITS, max_body_bytes: 2_048 })).toMatch(
      /^This file is 2\.9 KB; this server compares files up to 2\.0 KB\./,
    );
    expect(limitsLine(LIMITS)).toBe(
      "Up to 16.0 MB and 5,000 records, UTF-8 RIS (Publish or Perish, Zotero and EndNote export it).",
    );
    expect(limitsLine({ ...LIMITS, ...fixture.limits.compare })).toContain("5,000 records");
  });

  it("names a download by index, query hash and list", () => {
    const c = fixture.response;
    const hash = c.query.canonical_hash.slice(0, 12);
    expect(downloadName(c, "kept", "csv")).toBe(`openproceedings-${c.index_version}-${hash}-kept.csv`);
    expect(downloadName(c, "not_in_index", "csv")).toBe(
      `openproceedings-${c.index_version}-${hash}-not-in-index.csv`,
    );
    expect(downloadName(c, "added", "ris")).toBe(`openproceedings-${c.index_version}-${hash}-added.ris`);
    const odd = { index_version: "../x", query: { ...c.query, canonical_hash: 'a"b/../c' } };
    expect(downloadName(odd, "kept", "csv")).toBe("openproceedings-index-query-kept.csv");
  });
});
