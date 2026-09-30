import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import type { ParseResponse } from "@/editor/parse";
import { copy, RECORDS, type RecordCase } from "@/test/record-fixture";
import {
  allNegative,
  builtFrom,
  citabilityCaution,
  clausesOf,
  methodsText,
  removedBuckets,
  type SearchRecord,
} from "./methods-text";

const URL = "https://openproceedings.example/record/Ab3dE5fG7hJ9";

/** A record case with its record made citable and crawled: the fixture's corpus is RIS-only (never citable). */
function citable(c: RecordCase): {
  record: SearchRecord;
  canonical: ParseResponse;
  identification: ParseResponse;
} {
  const record = copy(c.stored.record);
  record.identification_citable = true;
  record.crawl_dates_kind = Object.fromEntries(Object.keys(record.crawl_dates).map((k) => [k, "crawl"]));
  return { record, canonical: copy(c.parse_canonical), identification: copy(c.parse_identification) };
}

function textOf(c: RecordCase): { text: string; record: SearchRecord } {
  const { record, canonical, identification } = citable(c);
  return {
    record,
    text: methodsText({ record, parseCanonical: canonical, parseIdentification: identification, url: URL }),
  };
}

/** The removed buckets as the text must itemise them, read from the record the API sent. */
function bucketsOf(record: SearchRecord): string {
  const items = [...Object.entries(record.excluded.track), ...Object.entries(record.excluded.status)]
    .filter(([v, n]) => v !== "unknown" && n > 0)
    .map(([v, n]) => `${n.toLocaleString("en-US")} ${v}`);
  return items.length === 0 ? "" : ` (${items.join(", ")})`;
}

const date = (iso: string) => iso.slice(0, 10);

describe("spec 05 §Components 8, verbatim (AC#1)", () => {
  /** The example in the spec, whitespace collapsed: the text this module must write for the same record. */
  function specExample(): string {
    const spec = readFileSync(path.join(import.meta.dirname, "../../../docs/specs/05-frontend.md"), "utf-8");
    const match = /\*"(We searched openproceedings[\s\S]*?)"\*/.exec(spec);
    if (match?.[1] === undefined) throw new Error("spec 05 no longer holds the methods-text example");
    return match[1].replace(/\s+/g, " ");
  }

  /** `/parse`'s report of `canonical`: each clause's span found in it, as the server reports them. */
  function parseOf(canonical: string, clauses: Record<"year" | "track" | "status", string>): ParseResponse {
    const at = (text: string): [number, number] => {
      const i = canonical.indexOf(text);
      if (i < 0) throw new Error(`${text} is not in ${canonical}`);
      return [i, i + text.length];
    };
    const end = canonical.length;
    const none = { negated: false, toggleable: true, reason: null, blocking_spans: [] };
    return {
      ...copy(RECORDS.limits.parse_canonical),
      canonical,
      query_version: "2",
      defaults: ["track", "status"],
      filters: {
        venue: { ...none, field: "venue", span: [end, end], values: ["ICLR", "ICML", "NeurIPS"] },
        year: { ...none, field: "year", span: at(clauses.year), ranges: [{ lo: 2020, hi: 2026 }] },
        track: {
          ...none,
          field: "track",
          span: at(clauses.track),
          values: ["datasets_benchmarks", "main", "position"],
        },
        status: { ...none, field: "status", span: at(clauses.status), values: ["accepted"] },
      },
    };
  }

  it("writes the spec's example sentence for sentence, the full index_version included", () => {
    const idq = '(("foundation model" OR llm) AND trust* AND year:2020..2026)';
    const canonical =
      '(("foundation model" OR llm) AND trust* AND year:2020..2026 AND ' +
      "track:(main OR datasets_benchmarks OR position) AND status:accepted)";
    const snapshot = "7c1e0d4b9a8f7e6d5c4b3a2918273645";
    const record: SearchRecord = {
      ...copy(RECORDS.limits.stored.record),
      input: idq,
      mode: "native",
      canonical,
      identification_query: idq,
      index_version: "a1b2c3d4e5f6",
      query_version: "2",
      snapshot_hash: snapshot,
      searched_at: "2026-09-25T14:03:11Z",
      crawl_dates: { "*": { from: "2026-09-18T06:00:00Z", to: "2026-09-20T21:30:00Z" } },
      crawl_dates_kind: { "*": "crawl" },
      identification_citable: true,
      identified_total: 716,
      total: 412,
      unclassified_total: 0,
      excluded: {
        total: 304,
        track: { workshop: 212, competition: 4, unknown: 0 },
        status: { rejected: 88, unknown: 0 },
      },
      translations: [],
    };
    const parse = parseOf(canonical, {
      year: "year:2020..2026",
      track: "track:(main OR datasets_benchmarks OR position)",
      status: "status:accepted",
    });
    const expected = specExample()
      .replace("<identification_query>", idq)
      .replace("<snapshot_hash>", snapshot)
      .replace("<url>", URL);
    expect(methodsText({ record, parseCanonical: parse, parseIdentification: null, url: URL })).toBe(
      expected,
    );
  });
});

describe("the methods text for the API's own records (every number is the record's)", () => {
  it("cites the reader's limit, both default clauses, the itemised buckets and the unclassified count", () => {
    const { record, text } = textOf(RECORDS.limits);
    const window = record.crawl_dates["*"];
    expect(window).toBeDefined();
    expect(text).toBe(
      `We searched openproceedings on ${date(record.searched_at)} (index \`${record.index_version}\`, built ` +
        `from a crawl run ${date(window?.from ?? "")} to ${date(window?.to ?? "")}) with the string ` +
        `\`${record.identification_query}\`, which identified ${record.identified_total} records within the ` +
        "limits it states (`year:2020..2026`). " +
        `The input as typed was \`${record.input}\`. ` +
        "Default filters `track:(datasets_benchmarks OR main OR position)` and `status:accepted` removed " +
        `${record.excluded.total} of them before screening${bucketsOf(record)}; that count includes ` +
        `${record.unclassified_total} unclassified records (track or status unknown), itemised separately. ` +
        "Cross-source duplicates were merged at ingest, before indexing (merge counts, and look-alike pairs " +
        "kept apart by track or venue-year, are in the search record). " +
        `Database scope: coverage report for snapshot \`${record.snapshot_hash}\`. ` +
        `${record.total} records were screened. Search record: ${URL}.`,
    );
  });

  it("holds no number the API didn't send (outside the quoted strings and the URL)", () => {
    for (const c of Object.values(RECORDS)) {
      const { record, text } = textOf(c);
      const sent = new Set(JSON.stringify(record).match(/\d+/g) ?? []);
      const prose = text.replace(/`[^`]*`/g, "").replace(URL, "");
      for (const n of prose.match(/\d[\d,]*/g) ?? []) {
        expect(sent, `${n} in: ${prose}`).toContain(n.replaceAll(",", ""));
      }
      // and the counts it must cite are each there
      for (const n of [
        record.identified_total,
        record.excluded.total,
        record.unclassified_total,
        record.total,
      ]) {
        expect(prose).toContain(n.toLocaleString("en-US"));
      }
    }
  });

  it('reads "all indexed records" when the identification string is empty', () => {
    const { record, text } = textOf(RECORDS.defaults_only);
    expect(record.identification_query).toBe("");
    expect(text).toContain(
      `with no search string (all indexed records), which identified ${record.identified_total} records with no limits.`,
    );
    expect(text).not.toContain("The input as typed");
  });

  it("cites the canonical string when the identification string is all-negative", () => {
    const { record, text } = textOf(RECORDS.all_negative);
    expect(allNegative(record, RECORDS.all_negative.parse_identification)).toBe(true);
    expect(text).toContain(
      `with the string \`${record.canonical}\`, which without its default filters identified ` +
        `${record.identified_total} records with no limits.`,
    );
    expect(text).not.toContain(`with the string \`${record.identification_query}\``);
  });

  it("names one default filter, and the reader's own track clause as a limit", () => {
    const { record, text } = textOf(RECORDS.one_default);
    expect(text).toContain("within the limits it states (`track:(main OR workshop)`).");
    expect(text).toContain(`Default filter \`status:accepted\` removed ${record.excluded.total} of them`);
  });

  it("gives the Scholar translation sentence, one clause per recorded code, and no nested filter as a limit", () => {
    const { record, text } = textOf(RECORDS.scholar);
    expect(text).toContain(`The input as typed was \`${record.input}\`. `);
    expect(text).toContain(
      "The string was entered in Google Scholar syntax and translated as recorded: `source:` values became " +
        "`venue:` filters; openproceedings does not stem (terms listed in the record).",
    );
    expect(text).not.toContain("unquoted multi-word");
    expect(text).toContain("with no limits."); // venue: sits inside an OR: the string states it
  });

  it("says no translation was recorded for a Scholar record without any", () => {
    const { record, canonical, identification } = citable(RECORDS.scholar);
    record.translations = [];
    const text = methodsText({
      record,
      parseCanonical: canonical,
      parseIdentification: identification,
      url: URL,
    });
    expect(text).toContain("The string was entered in Google Scholar syntax; no translation was recorded.");
  });

  it("words a translation code this version doesn't know with its recorded message", () => {
    const { record, canonical, identification } = citable(RECORDS.scholar);
    record.translations = [
      { code: "COMPAT_FUTURE", message: "`~` became NEAR/5", span: null, reading: null },
    ];
    const text = methodsText({
      record,
      parseCanonical: canonical,
      parseIdentification: identification,
      url: URL,
    });
    expect(text).toContain("translated as recorded: `~` became NEAR/5.");
  });

  it("doesn't separate the clauses when /parse ran under another query version", () => {
    const { record, canonical, identification } = citable(RECORDS.limits);
    canonical.query_version = `${record.query_version}-next`;
    identification.query_version = canonical.query_version;
    expect(clausesOf(record, canonical)).toBeNull();
    const text = methodsText({
      record,
      parseCanonical: canonical,
      parseIdentification: identification,
      url: URL,
    });
    expect(text).toContain("within any limits it states.");
    expect(text).toContain(
      `The default filters (written out in the canonical query \`${record.canonical}\`) removed`,
    );
  });

  it("doesn't separate the clauses without a report, or with one for another string", () => {
    const { record, canonical } = citable(RECORDS.limits);
    expect(clausesOf(record, null)).toBeNull();
    expect(clausesOf(record, { ...canonical, canonical: "trust" })).toBeNull();
    expect(clausesOf(record, canonical)).toEqual({
      defaults: ["track:(datasets_benchmarks OR main OR position)", "status:accepted"],
      limits: ["year:2020..2026"],
    });
  });

  it("uses singular words for a count of one", () => {
    const { record: base, canonical, identification } = citable(RECORDS.limits);
    const record = { ...base, total: 1, unclassified_total: 1 };
    const text = methodsText({
      record,
      parseCanonical: canonical,
      parseIdentification: identification,
      url: URL,
    });
    expect(text).toContain("1 record was screened.");
    expect(text).toContain("includes 1 unclassified record (track");
  });

  it("itemises the buckets in the API's order, unknown apart and zeros left out", () => {
    const record = copy(RECORDS.one_default.stored.record);
    expect(record.excluded.track).toEqual({ unknown: 0 });
    expect(removedBuckets(record)).toEqual(
      Object.entries(record.excluded.status)
        .filter(([v]) => v !== "unknown")
        .map(([v, n]) => `${n} ${v}`),
    );
  });
});

describe("the crawl window and the citability caution", () => {
  const record = () => copy(RECORDS.limits.stored.record);

  it("words the window by its kind, never as one date", () => {
    const r = record();
    const w = r.crawl_dates["*"];
    const span = `${date(w?.from ?? "")} to ${date(w?.to ?? "")}`;
    // the fixture is RIS-only: its window is when the Scholar searches were run
    expect(builtFrom(r)).toBe(`Scholar searches run ${span} (local time)`);
    r.crawl_dates_kind = { "*": "crawl" };
    expect(builtFrom(r)).toBe(`a crawl run ${span}`);
    r.crawl_dates_kind = { "*": "mixed" };
    expect(builtFrom(r)).toBe(`crawls and Scholar searches run ${span} (Scholar dates in local time)`);
    r.crawl_dates_kind = null;
    expect(builtFrom(r)).toBe(`records collected ${span}`);
    r.crawl_dates = {};
    expect(builtFrom(r)).toBeNull();
  });

  it("gives the CLI's caution unless identification_citable is exactly true", () => {
    const r = record();
    expect(r.identification_citable).toBe(false);
    expect(citabilityCaution(r)).toBe(
      `bootstrap corpus (sources: ${(r.sources ?? []).join(", ")}): these counts describe that corpus, not a ` +
        "database; they are not PRISMA identification numbers",
    );
    r.identification_citable = null;
    expect(citabilityCaution(r)).toBe(
      "not recorded whether this index is a bootstrap corpus: these counts may not be PRISMA identification numbers",
    );
    r.identification_citable = true;
    expect(citabilityCaution(r)).toBeNull();
  });
});
