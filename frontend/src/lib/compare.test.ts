import { describe, expect, it, vi } from "vitest";
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
  reasonLines,
  detailText,
  summaryText,
  fileSha256,
  undecidedText,
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
  max_upload_seconds: 30,
  max_concurrent: 1,
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
    for (const reason of [
      "query_limit",
      "filtered",
      "full_text",
      "stemming",
      "compat_reading",
      "unsettled",
      "our_bug",
    ]) {
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
    expect(matchedByText("doi")).toBe("matched by its DOI"); // TASK-186: Scopus and Web of Science exports
    // a record with neither names its links and its DOI as unmatched alike (TASK-186)
    expect(matchedByText("not_found")).toBe(
      "no record with this title in that venue and year, and no link or DOI naming an indexed paper",
    );
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

  it("writes each reason's count as a sentence with what to do, in the server's order", () => {
    expect(reasonLines("dropped", fixture.response.reason_totals.dropped, "scholar")).toEqual([
      "2 papers are excluded by a default filter: to include such a paper, write its track or status into " +
        "the query (its row says which).",
      "2 papers match only as another word form: type * after its stem (e.g. evaluat*) to match its other " +
        "forms; $ adds only one letter or digit (the Add $ action under the query).",
      "2 papers have no exact match in their title or abstract: no form of this query finds such a paper by " +
        "its title or abstract; keep it from your own file if it belongs in the review.",
    ]);
    // the Add $ action is under the query in Scholar mode only (USAB-R2-1); * reaches -ed and -ing forms,
    // which $ (one more letter or digit) cannot (R3-2)
    expect(reasonLines("dropped", { stemming: 1 }, "native")).toEqual([
      "1 paper matches only as another word form: type * after its stem (e.g. evaluat*) to match its other " +
        "forms; $ adds only one letter or digit.",
    ]);
    expect(reasonLines("kept", fixture.response.reason_totals.kept, "native")).toEqual([]);
    expect(reasonLines("added", { scholar_missed: 154 }, "native")).toEqual([
      "154 papers match exactly and are not in your file.",
    ]);
    expect(reasonLines("added", { scholar_missed: 1 }, "native")).toEqual([
      "1 paper matches exactly and is not in your file.",
    ]);
    expect(reasonLines("not_in_index", { coverage_gap: 3 }, "native")).toEqual([
      "3 papers are not in the index. Keep such a paper from your own file; no query here can find it.",
    ]);
    // a paper the query's own limit leaves out (TASK-185), with the API's own count for it
    const limited = fixture.limited.response.reason_totals.dropped;
    expect(reasonLines("dropped", { query_limit: limited.query_limit ?? 0 }, "native")).toEqual([
      `${limited.query_limit} papers are outside a limit your query writes: to include such a paper, widen ` +
        "that limit in the query (its row names the clause).",
    ]);
    // a paper the index doesn't hold whose year or venue in the file is outside the query's own limit: no
    // widening finds it, so its step is the coverage gap's, never "widen that limit" (gate UX/USAB MUST)
    const missing = fixture.limited.response.reason_totals.not_in_index;
    expect(missing.query_limit).toBe(1);
    expect(reasonLines("not_in_index", { query_limit: missing.query_limit ?? 0 }, "native")).toEqual([
      "1 paper is not in the index, and its year or venue in your file is outside a limit your query writes. " +
        "Keep such a paper from your own file; no query here can find it.",
    ]);
    expect(reasonLines("not_in_index", { query_limit: 2 }, "native")).toEqual([
      "2 papers are not in the index, and their year or venue in your file is outside a limit your query " +
        "writes. Keep such a paper from your own file; no query here can find it.",
    ]);
    const row = fixture.limited.response.not_in_index.find((r) => r.reason === "query_limit");
    expect(reasonText("not_in_index", row?.reason ?? null)).toBe(
      "not in the index; its year or venue in your file is outside a limit your query writes",
    );
    expect(reasonText("dropped", "query_limit")).toBe(
      "outside a limit your query writes (its year, venue, track or status)",
    );
    expect(reasonLines("dropped", { a_new_class: 2 }, "native")).toEqual(["2 papers: a_new_class."]); // open enum
    // every reason the API documents has its sentence, in both lists it can appear in, and a dropped or
    // missing paper's always says what to do next (USAB-S3)
    for (const reason of [
      "query_limit",
      "filtered",
      "full_text",
      "stemming",
      "compat_reading",
      "coverage_gap",
      "unsettled",
      "our_bug",
    ]) {
      const [line = ""] = reasonLines("dropped", { [reason]: 2 }, "native");
      expect(line).not.toContain(reason);
      expect(line).toMatch(/(: |\. [A-Z]).+\.$/);
      // one colon at most outside a parenthesis (USAB-R2-N)
      expect(line.replace(/\([^)]*\)/g, "").split(":").length).toBeLessThanOrEqual(2);
      expect(line).not.toContain("`");
    }
    for (const reason of ["scholar_missed", "compat_reading", "scholar_cap", "our_bug"]) {
      expect(reasonLines("added", { [reason]: 2 }, "native")[0]).not.toContain(reason);
    }
  });

  it("names what a person must decide, never just that one must", () => {
    expect(undecidedText("dropped", { reason: "full_text", settled: true })).toBe("");
    expect(undecidedText("not_in_index", { reason: "coverage_gap", settled: false })).toMatch(
      /^to check: is it in the index/,
    );
    expect(undecidedText("dropped", { reason: "unsettled", settled: false })).toMatch(
      /^to check: does the paper/,
    );
    expect(undecidedText("dropped", { reason: "our_bug", settled: false })).toMatch(/^to report/);
  });

  it("leaves out of a missing paper's evidence what its match line already says", () => {
    const unmatched = "no forum id, proceedings id, DOI or title+venue+year match in the snapshot";
    expect(detailText("not_in_index", { detail: unmatched })).toBe("");
    expect(detailText("not_in_index", { detail: `${unmatched}; its links are on a.example` })).toBe(
      "its links are on a.example",
    );
    expect(detailText("dropped", { detail: unmatched })).toBe(unmatched); // only where matched_by says it
  });

  it("sums a comparison up in one citable sentence (decision-043, prisma-reporting)", () => {
    const c = fixture.response;
    const sha = "a".repeat(64);
    const text = summaryText(c, { name: "mine.ris", sha256: sha }, "2026-10-05");
    const n = (x: number) => x.toLocaleString("en-US");
    expect(text).toBe(
      "As a search-development check (not a PRISMA flow-diagram count), on 2026-10-05 (UTC) we compared the " +
        `RIS file mine.ris (sha256 \`${sha}\`; ${n(c.records_total)} records read: ${n(c.papers_total)} papers ` +
        `compared, ${n(c.not_compared_total)} not compared (venue not recognised, or outside the indexed venues and years), and ` +
        `${n(c.duplicates_total)} ${c.duplicates_total === 1 ? "repeat" : "repeats"} of a paper already counted) ` +
        `with the query \`${c.query.canonical}\` (canonical_hash \`${c.query.canonical_hash}\`) on ` +
        `openproceedings (index \`${c.index_version}\`): ${n(c.kept_total)} kept, ${n(c.dropped_total)} dropped, ` +
        `${n(c.not_in_index_total)} not in the index, and ${n(c.added_total)} papers added that the file ` +
        "doesn't hold.",
    );
    // one sentence: no full stop before its end but the ones inside the query
    expect(text.replace(c.query.canonical, "").slice(0, -1)).not.toMatch(/\.\s/);
    // the file's records are all accounted for: compared, not compared, repeats (the fixture has each)
    expect(c.not_compared_total).toBeGreaterThan(0);
    expect(c.duplicates_total).toBeGreaterThan(0);
    expect(c.papers_total + c.not_compared_total + c.duplicates_total).toBe(c.records_total);
  });

  it("says when this browser couldn't compute the file's sha256, and counts one of a kind", () => {
    const one = {
      ...fixture.response,
      records_total: 1,
      papers_total: 1,
      not_compared_total: 0,
      duplicates_total: 0,
      added_total: 1,
    };
    const text = summaryText(one, { name: "mine.ris", sha256: null }, "2026-10-05");
    // no repeats: the clause is left out, never "0 repeats"
    expect(text).toContain(
      "(sha256 not computed by this browser: compute it from your copy; 1 record read: 1 paper compared and 0 " +
        "not compared (venue not recognised, or outside the indexed venues and years))",
    );
    expect(text).toContain("and 1 paper added that the file doesn't hold.");
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
  it("has its sha256 computed here from the bytes sent", async () => {
    // sha256 of the three bytes "abc" (FIPS 180-2's first example)
    expect(await fileSha256(new Blob(["abc"]))).toBe(
      "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
    );
    expect(await fileSha256(new Blob([fixture.file]))).toMatch(/^[0-9a-f]{64}$/);
  });

  it("has no sha256 where this browser has no Web Crypto (not a secure context)", async () => {
    vi.stubGlobal("crypto", {});
    try {
      expect(await fileSha256(new Blob(["abc"]))).toBeNull();
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("is checked against the instance's cap before it is sent", () => {
    expect(fileProblem({ size: 0 }, LIMITS)).toMatch(/empty/);
    expect(fileProblem({ size: LIMITS.max_body_bytes }, LIMITS)).toBeNull();
    expect(fileProblem({ size: LIMITS.max_body_bytes + 1 }, LIMITS)).toBe(
      "This file is 16.0 MB; this instance compares files up to 16.0 MB. Export it without abstracts (only " +
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
      /^This file is 2\.9 KB; this instance compares files up to 2\.0 KB\./,
    );
    // no upload time: behind the shipped proxy a browser's upload meets the proxy's own timeout, not the API's
    // `max_upload_seconds` (that bounds a direct client only; deploy/README.md), so the line names neither
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
