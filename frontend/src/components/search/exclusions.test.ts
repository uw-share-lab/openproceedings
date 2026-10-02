import { describe, expect, it } from "vitest";
import type { ParsedFilters } from "@/lib/search-state";
import { HOSTILE, quotedSafely } from "@/test/hostile";
import { bannerOf, clauseText, defaultsText, limitsOf } from "./exclusions";

const clause = (
  field: "venue" | "track" | "status",
  span: [number, number] | null,
  values: string[] | null,
) => ({
  field,
  negated: false,
  span,
  toggleable: span !== null,
  reason: span === null ? ("multiple_clauses" as const) : null,
  blocking_spans: [] as [number, number][],
  values,
});

/** `/parse`'s filters for `trust` (from the backend's `filter_clauses`): every field applied or unrestricted. */
const TRUST: ParsedFilters = {
  venue: clause("venue", [5, 5], ["ICLR", "ICML", "NeurIPS"]),
  year: {
    field: "year",
    negated: false,
    span: [5, 5],
    toggleable: true,
    reason: null,
    blocking_spans: [],
    ranges: [{ lo: 1000, hi: 9999 }],
  },
  track: clause("track", [5, 5], ["datasets_benchmarks", "main", "position"]),
  status: clause("status", [5, 5], ["accepted"]),
};

const EXCLUDED = {
  total: 304,
  track: { workshop: 212, competition: 4, unknown: 0 },
  status: { rejected: 88, unknown: 0 },
};
const FACETS = {
  venue: { NeurIPS: 180, ICLR: 151, ICML: 81 },
  year: { "2024": 141 },
  track: { main: 301, datasets_benchmarks: 64, position: 47, workshop: 205, competition: 4 },
  status: { accepted: 412, rejected: 88 },
};

describe("bannerOf (design W5 banner; BN-1–3)", () => {
  it("line 1 lists track buckets then status buckets in the API's order, leaving out unknown and zeros", () => {
    const b = bannerOf(EXCLUDED, FACETS, ["track", "status"], TRUST);
    expect(b.excluded).toBe("excluded: 212 workshop · 4 competition · 88 rejected");
    expect(b.unclassified).toBe("unclassified: 0 track unknown · 0 status unknown");
    expect(b.defaultClauses).toEqual(["track:(datasets_benchmarks OR main OR position)", "status:accepted"]);
  });

  it("says `excluded: none` when nothing is excluded, and keeps the unclassified line", () => {
    const b = bannerOf(
      { total: 3, track: { unknown: 3 }, status: { unknown: 0 } },
      FACETS,
      ["track", "status"],
      TRUST,
    );
    expect(b.excluded).toBe("excluded: none");
    expect(b.unclassified).toBe("unclassified: 3 track unknown · 0 status unknown");
    // the facet has no unknown track papers left once status:accepted applies: the include adds none
    expect(b.includes.map((i) => i.label)).toEqual([
      "include track unknown (adds 0: all 3 also fail status:accepted)",
    ]);
  });

  it("labels an include with the facet count, not the bucket, and its name carries the same number (M1)", () => {
    const b = bannerOf(EXCLUDED, FACETS, ["track", "status"], TRUST);
    const workshop = b.includes.find((i) => i.value === "workshop");
    expect(workshop?.bucket).toBe(212);
    expect(workshop?.label).toBe("include 205 workshop");
    expect(workshop?.name).toBe("Include 205 workshop papers");
    expect(workshop?.description).toBe(
      "Adds workshop to the track filter, `track:(… OR workshop)`; the track filter then becomes a limit you wrote.",
    );
    for (const i of b.includes) {
      const n = /\d[\d,]*/.exec(i.label)?.[0];
      expect(n).toBeDefined();
      expect(i.name).toContain(n);
    }
    expect(b.includes.map((i) => i.label)).toEqual([
      "include 205 workshop",
      "include 4 competition",
      "include 88 rejected",
    ]);
  });

  it("says when an include adds nothing, naming the other default (S5)", () => {
    const b = bannerOf(
      { total: 3, track: { workshop: 3, unknown: 0 }, status: { unknown: 0 } },
      { ...FACETS, track: { main: 1 } },
      ["track", "status"],
      TRUST,
    );
    expect(b.includes[0]?.label).toBe("include workshop (adds 0: all 3 also fail status:accepted)");
    expect(b.includes[0]?.adds).toBe(0);
  });

  it("names a field that is a limit the reader wrote, and drops its map from the unclassified line (M2)", () => {
    const b = bannerOf(
      { total: 88, track: { unknown: 0 }, status: { rejected: 88, unknown: 1 } },
      FACETS,
      ["status"],
      { ...TRUST, track: clause("track", [6, 30], ["main", "workshop"]) },
    );
    expect(b.excluded).toBe("excluded: 88 rejected · track: your limit applies (see Limits you wrote)");
    expect(b.unclassified).toBe("unclassified: 1 status unknown");
    expect(b.limitFields).toEqual(["track"]);
    expect(b.includes.map((i) => [i.field, i.value])).toEqual([
      ["status", "rejected"],
      ["status", "unknown"],
    ]);
    expect(b.defaultClauses).toEqual(["status:accepted"]);
  });

  it("itemises both maps and names no limit before /parse has answered", () => {
    const b = bannerOf(EXCLUDED, FACETS, null, null);
    expect(b.limitFields).toEqual([]);
    expect(b.unclassified).toBe("unclassified: 0 track unknown · 0 status unknown");
    expect(b.includes[0]?.label).toBe("include 205 workshop");
  });

  it("writes thousands with separators", () => {
    const b = bannerOf(
      { total: 1340, track: { workshop: 1340, unknown: 0 }, status: { unknown: 0 } },
      { ...FACETS, track: { workshop: 1200 } },
      ["track", "status"],
      TRUST,
    );
    expect(b.excluded).toBe("excluded: 1,340 workshop");
    expect(b.includes[0]?.label).toBe("include 1,200 workshop");
  });
});

describe("limitsOf (design W5 Limits line; RH-4, BN-5)", () => {
  const vocab = {
    venue: ["NeurIPS", "ICLR", "ICML"],
    track: ["main", "datasets_benchmarks", "position", "workshop", "competition", "unknown"],
  };

  it("lists nothing for a query whose only filters are defaults or unrestricted", () => {
    expect(limitsOf("trust", TRUST, ["track", "status"], FACETS, vocab)).toEqual([]);
  });

  it("slices each written clause from q (code points) and itemises what a single clause leaves out", () => {
    const q = "𝔘 trust year:2020..2022 track:(main OR workshop)";
    const filters: ParsedFilters = {
      ...TRUST,
      year: { ...TRUST.year, span: [8, 23], ranges: [{ lo: 2020, hi: 2022 }] },
      track: clause("track", [24, 48], ["main", "workshop"]),
    };
    const limits = limitsOf(
      q,
      filters,
      ["status"],
      { ...FACETS, track: { ...FACETS.track, unknown: 3 } },
      vocab,
    );
    expect(limits).toEqual([
      { field: "year", text: "year:2020..2022", leavesOut: [] },
      {
        field: "track",
        text: "track:(main OR workshop)",
        leavesOut: [
          ["datasets_benchmarks", 64],
          ["position", 47],
          ["competition", 4],
          ["unknown", 3],
        ],
      },
    ]);
  });

  it("lists a field with several clauses as such, so no limit is left off the line", () => {
    const filters: ParsedFilters = { ...TRUST, track: clause("track", null, null) };
    expect(limitsOf("trust track:main (track:workshop x)", filters, ["status"], FACETS, vocab)).toEqual([
      { field: "track", text: null, leavesOut: [] },
    ]);
  });
});

describe("clauseText", () => {
  it("writes one value bare and several grouped", () => {
    expect(clauseText("status", ["accepted"])).toBe("status:accepted");
    expect(clauseText("track", ["a", "b"])).toBe("track:(a OR b)");
  });
});

describe("values the API sent are clipped wherever a message quotes them (TASK-160)", () => {
  it.each(HOSTILE)(
    "an include's description quotes a bucket %j as %j, bare and in its clause",
    (value, shown) => {
      const b = bannerOf(
        { total: 5, track: { [value]: 5, unknown: 0 }, status: { unknown: 0 } },
        { ...FACETS, track: { [value]: 3 } },
        ["track", "status"],
        TRUST,
      );
      const description = b.includes[0]?.description ?? "";
      expect(description).toBe(
        `Adds ${shown} to the track filter, \`track:(… OR ${shown})\`; the track filter then becomes a limit you wrote.`,
      );
      quotedSafely(description);
      expect(b.includes[0]?.value).toBe(value); // the click still writes the value itself
    },
  );

  it.each(HOSTILE)("an include that adds 0 names the other default's value %j as %j", (value, shown) => {
    const b = bannerOf(
      { total: 3, track: { workshop: 3, unknown: 0 }, status: { unknown: 0 } },
      { ...FACETS, track: { main: 1 } },
      ["track", "status"],
      { ...TRUST, status: clause("status", [5, 5], [value]) },
    );
    // the label strips the clause's backticks; a clipped value has none of its own to lose
    const label = b.includes[0]?.label ?? "";
    expect(label).toBe(`include workshop (adds 0: all 3 also fail status:${shown})`);
    quotedSafely(label);
  });

  it.each(HOSTILE)("clauseText quotes a value %j as %j and keeps the field as written", (value, shown) => {
    expect(clauseText("status", [value])).toBe(`status:${shown}`);
    expect(clauseText("track", [value, "main"])).toBe(`track:(${shown} OR main)`);
  });

  it.each(HOSTILE)("the PRISMA disclosure quotes each default clause's value %j as %j", (value, shown) => {
    const b = bannerOf(EXCLUDED, FACETS, ["track", "status"], {
      ...TRUST,
      track: clause("track", [5, 5], [value, "main"]),
      status: clause("status", [5, 5], [value]),
    });
    const text = defaultsText(b.defaultClauses);
    expect(text).toBe(`The default filters \`track:(${shown} OR main)\` and \`status:${shown}\``);
    quotedSafely(text);
  });

  it("names the default filters in words when /parse has not reported them", () => {
    expect(defaultsText([])).toBe("The default filters");
  });
});
