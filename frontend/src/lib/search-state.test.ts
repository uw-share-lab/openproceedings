import { describe, expect, it } from "vitest";
import {
  INITIAL_STATE,
  MAX_PAGE,
  DEFAULT_LIMITS,
  PAGE_SIZE,
  SearchStateError,
  describeNotice,
  fromURL,
  noticeText,
  reduce,
  resultSetKey,
  searchHref,
  toSearchRequest,
  toURL,
  whyBlocked,
  clauseFromParse,
  yearClauseFromParse,
  formatYearClause,
  EVERY_YEAR,
  MAX_YEAR,
  MAX_YEAR_RANGES,
  MIN_YEAR,
  type ParsedYearClause,
  type YearClause,
  type YearRange,
  type ClauseReason,
  type FilterClause,
  type ParsedClause,
  type FilterField,
  type Mode,
  type QueryLimits,
  type SearchAction,
  type SearchState,
  type SearchStateErrorCode,
} from "./search-state";
import { codePointLength } from "@/api/spans";
import clauseGolden from "./filter-clause-golden.json";
import defaultLimits from "./default-limits.json";
import golden from "./wrap-golden.json";
import yearGolden from "./year-clause-golden.json";

const DEFAULT_TRACKS = ["main", "datasets_benchmarks", "position"];

/**
 * Asserts that `fn` throws a SearchStateError with `code`, and returns it. The message follows the
 * ux-writing pattern: "<what happened> — <why>. <How to fix>."
 */
function refused(fn: () => unknown, code: SearchStateErrorCode): SearchStateError {
  try {
    fn();
  } catch (e) {
    expect(e).toBeInstanceOf(SearchStateError);
    const err = e as SearchStateError;
    expect(err.code).toBe(code);
    expect(err.message).toMatch(/^\S.* — .+\. [A-Z].*\.$/);
    return err;
  }
  throw new Error(`expected a ${code} SearchStateError`);
}

const at = (q: string, overrides: Partial<SearchState> = {}): SearchState => ({
  ...INITIAL_STATE,
  q,
  ...overrides,
});

/** A clause the way /parse reports it for (source, mode): a code-point span into `source`. */
const clause = (
  field: FilterField,
  source: string,
  span: readonly [number, number],
  values: string[],
  mode: Mode = "native",
): FilterClause => ({ field, negated: false, source, mode, span, values });

/** A zero-width span at the end: the applied default (spec 02) or an unrestricted field. */
const atEnd = (field: FilterField, source: string, values: string[], mode: Mode = "native"): FilterClause =>
  clause(field, source, [[...source].length, [...source].length], values, mode);

describe("the URL holds the whole state", () => {
  // After any sequence of actions, writing the state to a URL and reading it back reproduces it exactly:
  // no filter (or anything else) can live in the state without living in the URL.
  const steps: SearchAction[] = [
    { type: "submit", q: "trust AND llm" },
    {
      type: "facetToggle",
      field: "track",
      value: "workshop",
      clause: atEnd("track", "trust AND llm", DEFAULT_TRACKS),
    },
    { type: "sort", sort: "year_desc" },
    { type: "page", page: 4 },
    { type: "setMode", mode: "scholar" },
    { type: "builderEdit", q: "(a OR b) AND c" },
    { type: "page", page: 2 },
  ];

  it("round-trips through the URL after every action", () => {
    let s = INITIAL_STATE;
    for (const step of steps) {
      s = reduce(s, step);
      const params = toURL(s);
      expect([...params.keys()].every((k) => ["q", "mode", "sort", "page"].includes(k))).toBe(true);
      expect(fromURL(new URLSearchParams(params.toString()))).toEqual({ state: s, notices: [] });
    }
  });

  it("sort and page never change the result-set key", () => {
    const s = at("trust AND benchmark*", { mode: "scholar" });
    const sorted = reduce(s, { type: "sort", sort: "year_desc" });
    const paged = reduce(sorted, { type: "page", page: 7 });
    expect(resultSetKey(sorted)).toEqual(resultSetKey(s));
    expect(resultSetKey(paged)).toEqual(resultSetKey(s));
    expect(resultSetKey(s)).toEqual(["trust AND benchmark*", "scholar"]);
  });

  it("a facet click changes the result set only by rewriting q", () => {
    const s = at("trust", { sort: "title", page: 3 });
    const after = reduce(s, {
      type: "facetToggle",
      field: "status",
      value: "rejected",
      clause: atEnd("status", "trust", ["accepted"]),
    });
    expect(after).toEqual({
      q: "(trust) AND status:(accepted OR rejected)",
      mode: "native",
      sort: "title",
      page: 1,
    });
  });
});

describe("writing a default out explicitly (wrap-golden.json, shared with the backend parser test)", () => {
  for (const c of golden.cases) {
    const action: SearchAction = {
      type: "facetToggle",
      field: c.field as FilterField,
      value: c.add,
      clause: atEnd(c.field as FilterField, c.q, c.values),
    };
    if ("expected" in c) {
      it(`${JSON.stringify(c.q)} → ${JSON.stringify(c.expected)}`, () => {
        expect(reduce(at(c.q), action).q).toBe(c.expected);
      });
    } else {
      it(`refuses ${JSON.stringify(c.q)}: a trailing escape would swallow the ')'`, () => {
        refused(() => reduce(at(c.q), action), "TRAILING_ESCAPE");
      });
    }
  }
});

/** A golden case of `filter-clause-golden.json`: what `/parse` reports for q, and what a click then does. */
interface ClauseGolden {
  readonly name: string;
  readonly q?: string;
  readonly q_parts?: readonly (readonly [string, number])[];
  readonly mode: Mode;
  readonly filters: Readonly<Record<string, unknown>>;
  readonly click: {
    readonly type: "facetToggle" | "includeExcluded";
    readonly field: FilterField;
    readonly value: string;
  };
  readonly expected?: string;
  readonly expected_parts?: readonly (readonly [string, number])[];
  readonly refused?: SearchStateErrorCode;
}

/** What each `/parse` reason's refusal must say (`FIELD` is the clicked field). */
const REASON_WORDING: Readonly<Record<ClauseReason, string>> = {
  multiple_clauses: "the query has more than one top-level `FIELD:` clause.",
  nested: "its only `FIELD:` clause is inside an OR or NOT.",
  mixed_fields: "its `FIELD:` clause is ORed with another field's clause.",
  negated: "The `FIELD:` clause is negated",
  too_long: `-character limit`,
  too_deep: `more than ${defaultLimits.max_query_depth} deep`,
  unparsable_edit: "the changed query would not parse.",
};

/** A golden string: as written, or its [text, times] runs concatenated. */
const spelled = (text: string | undefined, parts: ClauseGolden["q_parts"]): string =>
  text ?? (parts ?? []).map(([run, times]) => run.repeat(times)).join("");

describe("/parse filters → click (filter-clause-golden.json, shared with the backend's /parse tests)", () => {
  // The JSON is test data typed by hand; `ParsedClause` is the generated schema type the server fills.
  const cases = clauseGolden.cases as unknown as readonly ClauseGolden[];

  it("covers typed, default, pasted-canonical, astral, Scholar, nested, negated and both cap edges", () => {
    const reasons = new Set(
      cases.flatMap((c) => Object.values(c.filters).map((f) => (f as ParsedClause).reason)),
    );
    expect([...reasons].sort()).toEqual(
      [
        null,
        "multiple_clauses",
        "nested",
        "mixed_fields",
        "negated",
        "too_long",
        "too_deep",
        "unparsable_edit",
      ].sort(),
    );
  });

  for (const c of cases) {
    const q = spelled(c.q, c.q_parts);
    const parsed = c.filters[c.click.field] as ParsedClause;
    const { type, field, value } = c.click;
    const action = { type, field, value, ...clauseFromParse(parsed, q, c.mode) } as SearchAction;
    const state = at(q, { mode: c.mode });
    if (c.refused === undefined) {
      it(`${c.name}: writes the expected q`, () => {
        expect(reduce(state, action).q).toBe(spelled(c.expected, c.expected_parts));
      });
    } else {
      const code = c.refused;
      it(`${c.name}: refuses with ${code}, worded for its reason, and whyBlocked says so before the click`, () => {
        const err = refused(() => reduce(state, action), code);
        expect(whyBlocked(state, action)?.code).toBe(code);
        // Each reason has its own wording, never the generic one for a reason this code doesn't know.
        const fragment = parsed.reason === null ? undefined : REASON_WORDING[parsed.reason];
        expect(fragment, `a golden refusal's reason: ${String(parsed.reason)}`).toBeDefined();
        expect(err.message).toContain(fragment?.replaceAll("FIELD", field));
      });
    }
  }
});

describe("clauseFromParse", () => {
  const typed: ParsedClause = {
    field: "venue",
    negated: false,
    span: [6, 16],
    toggleable: true,
    reason: null,
    blocking_spans: [],
    values: ["ICLR"],
  };

  it("keys a toggleable clause by the query it was parsed from", () => {
    expect(clauseFromParse(typed, "trust venue:ICLR", "scholar")).toEqual({
      clause: {
        field: "venue",
        negated: false,
        source: "trust venue:ICLR",
        mode: "scholar",
        span: [6, 16],
        values: ["ICLR"],
      },
      reason: null,
    });
  });

  it("gives no clause, with the server's reason, for one that is not toggleable", () => {
    const negated: ParsedClause = { ...typed, negated: true, toggleable: false, reason: "negated" };
    expect(clauseFromParse(negated, "x", "native")).toEqual({ clause: null, reason: "negated" });
  });

  it("gives no clause and no reason when the query did not parse (filters is null)", () => {
    expect(clauseFromParse(null, "(x", "native")).toEqual({ clause: null, reason: null });
    expect(clauseFromParse(undefined, "(x", "native")).toEqual({ clause: null, reason: null });
  });

  it("never offers a year clause as a value list", () => {
    const year = { ...typed, field: "year" } as const;
    expect(clauseFromParse(year, "x", "native")).toEqual({ clause: null, reason: null });
  });

  it("offers no clause from inconsistent untyped /parse data that claims to be toggleable", () => {
    // The server's model refuses these (test_models_refuse_inconsistent_reports); a caller holding
    // hand-built or stale JSON still gets no clause, so the reducer refuses rather than splicing.
    for (const bad of [
      { ...typed, negated: true },
      { ...typed, span: null },
      { ...typed, values: null },
    ]) {
      const choice = clauseFromParse(bad as ParsedClause, "trust venue:ICLR", "native");
      expect(choice).toEqual({ clause: null, reason: null });
      const action = { type: "facetToggle", field: "venue", value: "ICML", ...choice } as const;
      refused(() => reduce(at("trust venue:ICLR"), action), "NO_EDITABLE_CLAUSE");
    }
  });

  it("words a reason it doesn't know generically (the reasons are an open set)", () => {
    const err = refused(
      () =>
        reduce(at("x"), {
          type: "facetToggle",
          field: "venue",
          value: "ICLR",
          clause: null,
          reason: "a_future_reason" as ClauseReason,
        }),
      "NO_EDITABLE_CLAUSE",
    );
    expect(err.message).toContain("more than one top-level `venue:` clause, or one inside an OR or NOT");
  });
});

describe("facetToggle rewrites q exactly", () => {
  it.each(["", "   "])(
    "refuses an empty query %j (never an empty group; /parse reports no clause for it)",
    (q) => {
      refused(
        () =>
          reduce(at(q), {
            type: "facetToggle",
            field: "track",
            value: "workshop",
            clause: atEnd("track", q, DEFAULT_TRACKS),
          }),
        "EMPTY_QUERY",
      );
    },
  );

  it("writes the grouped form field:(…) even for one value, so it never touches a following group", () => {
    const q = "trust track:(main OR workshop)";
    const one = reduce(at(q), {
      type: "facetToggle",
      field: "track",
      value: "workshop",
      clause: clause("track", q, [6, 30], ["main", "workshop"]),
    });
    expect(one.q).toBe("trust track:(main)");
    const before = "trust track:(main OR workshop)(x OR y)";
    const touching = reduce(at(before), {
      type: "facetToggle",
      field: "track",
      value: "main",
      clause: clause("track", before, [6, 30], ["main", "workshop"]),
    });
    expect(touching.q).toBe("trust track:(workshop)(x OR y)");
  });

  it("replaces a typed clause in place, removing a value", () => {
    const q = "trust AND track:(main OR workshop) AND year:2024";
    //         0         10                      34
    const next = reduce(at(q), {
      type: "facetToggle",
      field: "track",
      value: "workshop",
      clause: clause("track", q, [10, 34], ["main", "workshop"]),
    });
    expect(next.q).toBe("trust AND track:(main) AND year:2024");
  });

  it("replaces a single-value clause with a group when adding", () => {
    const q = "trust venue:ICLR";
    const next = reduce(at(q), {
      type: "facetToggle",
      field: "venue",
      value: "ICML",
      clause: clause("venue", q, [6, 16], ["ICLR"]),
    });
    expect(next.q).toBe("trust venue:(ICLR OR ICML)");
  });

  it("counts spans in code points, not UTF-16 units", () => {
    const q = "𝒜 track:main"; // 𝒜 is one code point, two UTF-16 units
    const next = reduce(at(q), {
      type: "facetToggle",
      field: "track",
      value: "workshop",
      clause: clause("track", q, [2, 12], ["main"]),
    });
    expect(next.q).toBe("𝒜 track:(main OR workshop)");
  });

  it("resets page but keeps mode and sort", () => {
    const q = "trust status:accepted";
    const next = reduce(at(q, { mode: "scholar", sort: "year_asc", page: 4 }), {
      type: "facetToggle",
      field: "status",
      value: "rejected",
      clause: clause("status", q, [6, 21], ["accepted"], "scholar"),
    });
    expect(next).toEqual({
      q: "trust status:(accepted OR rejected)",
      mode: "scholar",
      sort: "year_asc",
      page: 1,
    });
  });
});

describe("includeExcluded rewrites q exactly", () => {
  it("adds the excluded value to the default clause", () => {
    const next = reduce(at("trust"), {
      type: "includeExcluded",
      field: "status",
      value: "rejected",
      clause: atEnd("status", "trust", ["accepted"]),
    });
    expect(next.q).toBe("(trust) AND status:(accepted OR rejected)");
  });

  it("adds the value to a typed clause in place", () => {
    const q = "trust AND track:main AND llm";
    const next = reduce(at(q), {
      type: "includeExcluded",
      field: "track",
      value: "workshop",
      clause: clause("track", q, [10, 20], ["main"]),
    });
    expect(next.q).toBe("trust AND track:(main OR workshop) AND llm");
  });

  it("refuses a value that is already included", () => {
    refused(
      () =>
        reduce(at("trust"), {
          type: "includeExcluded",
          field: "track",
          value: "main",
          clause: atEnd("track", "trust", DEFAULT_TRACKS),
        }),
      "ALREADY_INCLUDED",
    );
  });
});

describe("filter rewrites refuse what they cannot do exactly", () => {
  it("refuses a field with no single editable clause (two top-level track: clauses on the flattened tree)", () => {
    // `track:workshop "large language model" AND (venue:NeurIPS track:workshop)`: splicing over the first
    // clause would leave the grouped one ANDed in, so adding `main` would change nothing. /parse reports none.
    const q = 'track:workshop "large language model" AND (venue:NeurIPS track:workshop)';
    for (const action of [
      { type: "facetToggle", field: "track", value: "main", clause: null },
      { type: "includeExcluded", field: "track", value: "main", clause: null },
    ] as const) {
      refused(() => reduce(at(q), action), "NO_EDITABLE_CLAUSE");
      expect(whyBlocked(at(q), action)?.code).toBe("NO_EDITABLE_CLAUSE");
    }
  });

  // `<pad> track:main` → `<pad> track:(main OR workshop)` adds 14 code points. The pad is astral, so a
  // UTF-16 length check would count it double and get this wrong.
  const addWorkshop = (length: number): SearchAction => {
    const pad = "𝒜".repeat(length - " track:main".length);
    const q = `${pad} track:main`;
    expect(codePointLength(q)).toBe(length);
    return {
      type: "facetToggle",
      field: "track",
      value: "workshop",
      clause: clause("track", q, [codePointLength(pad) + 1, length], ["main"]),
    };
  };
  const sourceOf = (a: SearchAction) => (a.type === "facetToggle" && a.clause ? a.clause.source : "");

  it("refuses a rewrite that would take q past the default max_query_length code points (1,994 + 14)", () => {
    const action = addWorkshop(1994);
    const e = refused(() => reduce(at(sourceOf(action)), action), "TOO_LONG");
    expect(e.message).toBe(
      "The changed query would be 2,008 characters long — the limit is 2,000. Shorten the query text first.",
    );
  });

  it("refuses a rewrite one code point past the default max_query_length (1,987 + 14)", () => {
    const action = addWorkshop(1987);
    refused(() => reduce(at(sourceOf(action)), action), "TOO_LONG");
  });

  it("allows a rewrite that lands exactly on the default max_query_length (1,986 + 14)", () => {
    const action = addWorkshop(1986);
    expect(codePointLength(reduce(at(sourceOf(action)), action).q)).toBe(DEFAULT_LIMITS.max_query_length);
  });

  it("refuses a wrap that would take q past the default max_query_length", () => {
    const q = "a".repeat(DEFAULT_LIMITS.max_query_length - 20);
    refused(
      () =>
        reduce(at(q), {
          type: "facetToggle",
          field: "track",
          value: "workshop",
          clause: atEnd("track", q, DEFAULT_TRACKS),
        }),
      "TOO_LONG",
    );
  });

  // TASK-089: the cap is the instance's, from `/meta`'s `limits`; the default only stands in until it is fetched.
  it("defaults the cap to default-limits.json, the file the backend's /meta contract test checks", () => {
    expect(DEFAULT_LIMITS).toEqual(defaultLimits);
  });

  it("takes the cap from the limits it is given (an instance whose /meta serves another cap)", () => {
    const action = addWorkshop(1986); // lands on 2,000: allowed by the default
    const limits: QueryLimits = { ...DEFAULT_LIMITS, max_query_length: 1999 };
    const e = refused(() => reduce(at(sourceOf(action)), action, limits), "TOO_LONG");
    expect(e.message).toBe(
      "The changed query would be 2,000 characters long — the limit is 1,999. Shorten the query text first.",
    );
    expect(whyBlocked(at(sourceOf(action)), action, limits)?.code).toBe("TOO_LONG");
    expect(
      whyBlocked(at(sourceOf(action)), action, { ...DEFAULT_LIMITS, max_query_length: 2000 }),
    ).toBeNull();
  });

  it("words /parse's too_long refusal with the given cap", () => {
    const e = refused(
      () =>
        reduce(
          at("trust"),
          { type: "facetToggle", field: "track", value: "workshop", clause: null, reason: "too_long" },
          { ...DEFAULT_LIMITS, max_query_length: 1234 },
        ),
      "TOO_LONG",
    );
    expect(e.message).toContain("over the 1,234-character limit");
  });

  it("words /parse's too_deep refusal with the given depth cap (/meta's max_query_depth)", () => {
    const action = {
      type: "includeExcluded",
      field: "track",
      value: "workshop",
      clause: null,
      reason: "too_deep",
    } as const;
    const e = refused(
      () => reduce(at("trust"), action, { ...DEFAULT_LIMITS, max_query_depth: 12 }),
      "TOO_DEEP",
    );
    expect(e.message).toContain("more than 12 deep");
    expect(refused(() => reduce(at("trust"), action), "TOO_DEEP").message).toContain("more than 64 deep");
  });

  it("refuses a clause parsed from a different q", () => {
    refused(
      () =>
        reduce(at("trust AND llm"), {
          type: "facetToggle",
          field: "track",
          value: "workshop",
          clause: atEnd("track", "trust", DEFAULT_TRACKS),
        }),
      "STALE_CLAUSE",
    );
  });

  it("refuses a clause parsed in the other mode (setMode after the clause was fetched)", () => {
    const fetched = atEnd("track", "trust", DEFAULT_TRACKS, "native");
    const s = reduce(at("trust"), { type: "setMode", mode: "scholar" });
    refused(
      () => reduce(s, { type: "facetToggle", field: "track", value: "workshop", clause: fetched }),
      "STALE_CLAUSE",
    );
  });

  it("refuses a clause for another field (a status clause passed as track)", () => {
    const q = "trust status:accepted";
    refused(
      () =>
        reduce(at(q), {
          type: "facetToggle",
          field: "track",
          value: "workshop",
          clause: clause("status", q, [6, 21], ["accepted"]),
        }),
      "WRONG_FIELD",
    );
  });

  it("refuses a negated clause: adding to -track:workshop would flip its meaning", () => {
    const q = "trust -track:workshop";
    const negated = { ...clause("track", q, [6, 21], ["workshop"]), negated: true };
    refused(
      () =>
        reduce(at(q), {
          type: "facetToggle",
          field: "track",
          value: "main",
          // @ts-expect-error a negated clause is not a FilterClause; the runtime check catches untyped callers
          clause: negated,
        }),
      "NEGATED_CLAUSE",
    );
  });

  it("refuses to remove the last value", () => {
    const q = "trust track:main";
    refused(
      () =>
        reduce(at(q), {
          type: "facetToggle",
          field: "track",
          value: "main",
          clause: clause("track", q, [6, 16], ["main"]),
        }),
      "LAST_VALUE",
    );
  });

  it("refuses a value that is not a bare identifier", () => {
    refused(
      () =>
        reduce(at("trust"), {
          type: "facetToggle",
          field: "venue",
          value: "ICLR) OR (x",
          clause: atEnd("venue", "trust", ["ICML"]),
        }),
      "BAD_VALUE",
    );
  });

  it("refuses a bad value already in the clause's values", () => {
    refused(
      () =>
        reduce(at("trust"), {
          type: "facetToggle",
          field: "venue",
          value: "ICML",
          clause: atEnd("venue", "trust", ["ICLR OR x"]),
        }),
      "BAD_VALUE",
    );
  });

  it("refuses a zero-width span that is not at the end", () => {
    refused(
      () =>
        reduce(at("trust"), {
          type: "facetToggle",
          field: "track",
          value: "workshop",
          clause: clause("track", "trust", [2, 2], DEFAULT_TRACKS),
        }),
      "BAD_SPAN",
    );
  });

  it("refuses a span outside q", () => {
    refused(
      () =>
        reduce(at("trust"), {
          type: "facetToggle",
          field: "track",
          value: "workshop",
          clause: clause("track", "trust", [3, 40], ["main"]),
        }),
      "BAD_SPAN",
    );
  });
});

describe("view and query actions", () => {
  it("submit replaces q, keeps sort, resets page", () => {
    const next = reduce(at("old", { sort: "title", page: 5 }), { type: "submit", q: "new" });
    expect(next).toEqual({ q: "new", mode: "native", sort: "title", page: 1 });
  });

  it("submit can switch mode", () => {
    expect(reduce(at("a"), { type: "submit", q: "b", mode: "scholar" }).mode).toBe("scholar");
  });

  it("builderEdit replaces q and resets page", () => {
    expect(reduce(at("a", { page: 2 }), { type: "builderEdit", q: "(a OR b) AND c" })).toEqual(
      at("(a OR b) AND c"),
    );
  });

  it("setMode and sort reset page; page does not reset anything", () => {
    expect(reduce(at("a", { page: 3 }), { type: "setMode", mode: "scholar" }).page).toBe(1);
    expect(reduce(at("a", { page: 3 }), { type: "sort", sort: "title" }).page).toBe(1);
    expect(reduce(at("a", { sort: "title" }), { type: "page", page: 9 })).toEqual(
      at("a", { sort: "title", page: 9 }),
    );
  });

  it("refuses a page that is not a positive integer up to MAX_PAGE", () => {
    for (const page of [0, 1.5, MAX_PAGE + 1]) {
      const e = refused(() => reduce(at("a"), { type: "page", page }), "BAD_PAGE");
      expect(e.message).toBe(
        `${page} is not a page number — a page is a whole number from 1 to 10,000. Choose a page in that range.`,
      );
    }
    expect(reduce(at("a"), { type: "page", page: MAX_PAGE }).page).toBe(MAX_PAGE);
  });
});

describe("URL ↔ state", () => {
  it("reads the whole state from the URL", () => {
    const { state, notices } = fromURL(
      new URLSearchParams("q=trust%20AND%20track%3Aworkshop&mode=scholar&sort=year_desc&page=3"),
    );
    expect(state).toEqual({ q: "trust AND track:workshop", mode: "scholar", sort: "year_desc", page: 3 });
    expect(notices).toEqual([]);
  });

  it("defaults an empty URL", () => {
    expect(fromURL(new URLSearchParams(""))).toEqual({ state: INITIAL_STATE, notices: [] });
  });

  it("keeps q verbatim, whitespace included", () => {
    expect(fromURL(new URLSearchParams({ q: "  trust  " })).state.q).toBe("  trust  ");
  });

  it("drops unknown params with a notice (a hidden filter cannot ride along)", () => {
    const { state, notices } = fromURL(new URLSearchParams("q=trust&track=workshop&venue=ICLR"));
    expect(state).toEqual(at("trust"));
    expect(notices).toEqual([
      { param: "track", value: "workshop", reason: "unknown_param" },
      { param: "venue", value: "ICLR", reason: "unknown_param" },
    ]);
  });

  it("falls back visibly on invalid values", () => {
    const { state, notices } = fromURL(new URLSearchParams("q=a&mode=bing&sort=random&page=-2"));
    expect(state).toEqual(at("a"));
    expect(notices).toEqual([
      { param: "mode", value: "bing", reason: "invalid_value", used: "native" },
      { param: "sort", value: "random", reason: "invalid_value", used: "relevance" },
      { param: "page", value: "-2", reason: "invalid_value", used: "1" },
    ]);
  });

  it.each(["0", "01", "1.5", "1e3", "", "9999999999", String(MAX_PAGE + 1), "123456"])(
    "rejects page=%j",
    (page) => {
      const { state, notices } = fromURL(new URLSearchParams({ page }));
      expect(state.page).toBe(1);
      expect(notices).toEqual([{ param: "page", value: page, reason: "invalid_value", used: "1" }]);
    },
  );

  it("accepts page=MAX_PAGE", () => {
    expect(fromURL(new URLSearchParams({ page: String(MAX_PAGE) }))).toEqual({
      state: { ...INITIAL_STATE, page: MAX_PAGE },
      notices: [],
    });
  });

  it("uses the first of a repeated param and says so", () => {
    const { state, notices } = fromURL(new URLSearchParams("q=a&q=b"));
    expect(state.q).toBe("a");
    expect(notices).toEqual([{ param: "q", value: "b", reason: "repeated_param", used: "a" }]);
  });

  it("writes q and mode always, sort and page only when not default", () => {
    expect(toURL(at("trust")).toString()).toBe("q=trust&mode=native");
    expect(toURL(at("a b", { mode: "scholar", sort: "title", page: 2 })).toString()).toBe(
      "q=a+b&mode=scholar&sort=title&page=2",
    );
    expect(searchHref(at("x:y"))).toBe("/search?q=x%3Ay&mode=native");
  });

  it.each<SearchState>([
    INITIAL_STATE,
    at("trust AND benchmark*"),
    at('"foundation model" OR 𝒜 & ü = +%', { mode: "scholar", sort: "year_asc", page: 12 }),
    at("  spaced  ", { sort: "title" }),
  ])("round-trips %j", (s) => {
    expect(fromURL(new URLSearchParams(toURL(s).toString()))).toEqual({ state: s, notices: [] });
  });
});

describe("URL notices", () => {
  it("lists q and mode notices first, since they say what was searched", () => {
    const { notices } = fromURL(new URLSearchParams("track=x&sort=bad&mode=bing&q=&q=trust"));
    expect(notices.map((n) => n.param)).toEqual(["q", "mode", "track", "sort"]);
  });

  it("names the repeated param, the value used and the one ignored, marking an empty value", () => {
    const [n] = fromURL(new URLSearchParams("q=&q=trust")).notices;
    expect(n && noticeText(n)).toBe(
      '`q` appears more than once; using the first value `""` and ignoring `trust`.',
    );
  });

  it("lists the valid values from the reducer's constants", () => {
    const texts = fromURL(new URLSearchParams("q=a&mode=bing&sort=random&page=0")).notices.map(noticeText);
    expect(texts).toEqual([
      "`mode=bing` is not a mode — modes are `native`, `scholar`. `q` was read as native syntax.",
      "`sort=random` is not a sort order — sort orders are `relevance`, `year_desc`, `year_asc`, `title`. " +
        "Sorted by `relevance` instead.",
      "`page=0` is not a page number — a page is a whole number from 1 to 10,000. Showing page 1 instead.",
    ]);
  });

  it("says an unknown param was ignored and lists the search parameters", () => {
    const [n] = fromURL(new URLSearchParams("q=a&track=workshop")).notices;
    expect(n && noticeText(n)).toBe(
      "`track=workshop` was ignored — `track` is not a search parameter. " +
        "Search parameters are `q`, `mode`, `sort`, `page`.",
    );
  });

  it("marks values as code runs so the page can set them in monospace", () => {
    const [n] = fromURL(new URLSearchParams("q=a&q=b")).notices;
    expect(n && describeNotice(n)).toEqual([
      { code: "q" },
      { text: " appears more than once; using the first value " },
      { code: "a" },
      { text: " and ignoring " },
      { code: "b" },
      { text: "." },
    ]);
  });
});

describe("whyBlocked (controls are disabled with the reason, not refused after the click)", () => {
  const action: SearchAction = {
    type: "facetToggle",
    field: "track",
    value: "workshop",
    clause: atEnd("track", "trust", DEFAULT_TRACKS),
  };

  it("is null when the action applies", () => {
    expect(whyBlocked(at("trust"), action)).toBeNull();
  });

  it("returns STALE_CLAUSE while the clause is from an earlier query", () => {
    expect(whyBlocked(at("trust AND llm"), action)?.code).toBe("STALE_CLAUSE");
  });

  it("returns ALREADY_INCLUDED for an include of an admitted value", () => {
    const include: SearchAction = {
      type: "includeExcluded",
      field: "track",
      value: "main",
      clause: atEnd("track", "trust", DEFAULT_TRACKS),
    };
    expect(whyBlocked(at("trust"), include)?.code).toBe("ALREADY_INCLUDED");
  });

  it("rethrows an error that is not a SearchStateError (a bug is never shown as a disabled control)", () => {
    const broken = {
      type: "facetToggle",
      field: "track",
      value: "workshop",
      get clause(): never {
        throw new TypeError("boom");
      },
    } as unknown as SearchAction;
    expect(() => whyBlocked(at("trust"), broken)).toThrow(TypeError);
  });
});

/** A golden case of `year-clause-golden.json`: `/parse`'s year report for q, and what a year action does. */
interface YearGolden {
  readonly name: string;
  readonly q?: string;
  readonly q_parts?: readonly (readonly [string, number])[];
  readonly mode: Mode;
  readonly year: ParsedYearClause;
  readonly action:
    | { readonly type: "yearSet" | "yearAdd" | "yearRemove"; readonly range: YearRange }
    | { readonly type: "yearClear" };
  readonly expected?: string;
  readonly expected_parts?: readonly (readonly [string, number])[];
  readonly ranges_after?: readonly YearRange[];
  readonly refused?: SearchStateErrorCode;
}

describe("year actions (year-clause-golden.json, shared with the backend's /parse tests)", () => {
  // The JSON is test data typed by hand; `ParsedYearClause` is the generated schema type the server fills.
  const cases = yearGolden.cases as unknown as readonly YearGolden[];

  it("uses the server's year bounds and range limit (the backend test reads the same file)", () => {
    expect([MIN_YEAR, MAX_YEAR, MAX_YEAR_RANGES]).toEqual([
      yearGolden.min_year,
      yearGolden.max_year,
      yearGolden.max_year_ranges,
    ]);
    expect(EVERY_YEAR).toEqual({ lo: MIN_YEAR, hi: MAX_YEAR });
  });

  it("covers every action, every /parse reason and every year refusal", () => {
    expect(new Set(cases.map((c) => c.action.type))).toEqual(
      new Set(["yearSet", "yearClear", "yearAdd", "yearRemove"]),
    );
    expect(new Set(cases.map((c) => c.year.reason))).toEqual(new Set([null, ...Object.keys(REASON_WORDING)]));
    expect(new Set(cases.flatMap((c) => (c.refused === undefined ? [] : [c.refused])))).toEqual(
      new Set([
        "TOO_MANY_RANGES",
        "ALREADY_INCLUDED",
        "NOT_INCLUDED",
        "LAST_VALUE",
        "BAD_VALUE",
        "NEGATED_CLAUSE",
        "NO_EDITABLE_CLAUSE",
        "TOO_DEEP",
        "TOO_LONG",
      ]),
    );
  });

  for (const c of cases) {
    const q = spelled(c.q, c.q_parts);
    const action = { ...c.action, ...yearClauseFromParse(c.year, q, c.mode) } as SearchAction;
    const state = at(q, { mode: c.mode, sort: "year_desc", page: 3 });
    if (c.refused === undefined) {
      it(`${c.name}: writes the expected q, grouped and merged`, () => {
        const expected = spelled(c.expected, c.expected_parts);
        expect(reduce(state, action)).toEqual({ ...state, q: expected, page: 1 });
        expect(whyBlocked(state, action)).toBeNull();
        // The clause written is exactly the ranges the server then reports (checked there against `expected`).
        expect(expected).toContain(formatYearClause(c.ranges_after ?? []));
      });
    } else {
      const code = c.refused;
      it(`${c.name}: refuses with ${code}, and whyBlocked says so before the click`, () => {
        const err = refused(() => reduce(state, action), code);
        expect(whyBlocked(state, action)?.code).toBe(code);
        if (c.year.reason !== null) {
          expect(err.message).toContain(REASON_WORDING[c.year.reason].replaceAll("FIELD", "year"));
        }
      });
    }
  }
});

describe("yearClauseFromParse and the year clause checks", () => {
  const typed: ParsedYearClause = {
    field: "year",
    negated: false,
    span: [6, 15],
    toggleable: true,
    reason: null,
    ranges: [{ lo: 2020, hi: 2020 }],
    blocking_spans: [],
  };
  const source = "trust year:2020";

  it("keys a toggleable clause by the query it was parsed from", () => {
    expect(yearClauseFromParse(typed, source, "scholar")).toEqual({
      clause: {
        field: "year",
        negated: false,
        source,
        mode: "scholar",
        span: [6, 15],
        ranges: [{ lo: 2020, hi: 2020 }],
      },
      reason: null,
    });
  });

  it("gives no clause, with the server's reason, for one that is not toggleable, and none for no report", () => {
    const negated: ParsedYearClause = { ...typed, negated: true, toggleable: false, reason: "negated" };
    expect(yearClauseFromParse(negated, source, "native")).toEqual({ clause: null, reason: "negated" });
    expect(yearClauseFromParse(null, "(x", "native")).toEqual({ clause: null, reason: null });
    expect(yearClauseFromParse(undefined, "(x", "native")).toEqual({ clause: null, reason: null });
  });

  const add = (s: SearchState, clause: ReturnType<typeof yearClauseFromParse>): SearchAction => ({
    type: "yearAdd",
    range: { lo: 2022, hi: 2022 },
    ...clause,
  });

  it("refuses a clause parsed from another query or mode (STALE_CLAUSE)", () => {
    const choice = yearClauseFromParse(typed, source, "native");
    refused(() => reduce(at(`${source} x`), add(at(source), choice)), "STALE_CLAUSE");
    refused(() => reduce(at(source, { mode: "scholar" }), add(at(source), choice)), "STALE_CLAUSE");
    expect(whyBlocked(at(`${source} x`), add(at(source), choice))?.code).toBe("STALE_CLAUSE");
  });

  it("refuses another field's clause, and a negated one passed untyped", () => {
    const clause = yearClauseFromParse(typed, source, "native").clause;
    const wrong = { ...clause, field: "venue" } as unknown as YearClause;
    refused(() => reduce(at(source), add(at(source), { clause: wrong, reason: null })), "WRONG_FIELD");
    const negated = { ...clause, negated: true } as unknown as YearClause;
    refused(() => reduce(at(source), add(at(source), { clause: negated, reason: null })), "NEGATED_CLAUSE");
  });

  it("refuses a non-integer year, and a report whose ranges are not years", () => {
    const choice = yearClauseFromParse(typed, source, "native");
    const half: SearchAction = { type: "yearSet", range: { lo: 2020.5, hi: 2021 }, ...choice };
    refused(() => reduce(at(source), half), "BAD_VALUE");
    const bad = { ...choice.clause, ranges: [{ lo: 20, hi: 20 }] } as unknown as YearClause;
    refused(() => reduce(at(source), add(at(source), { clause: bad, reason: null })), "BAD_VALUE");
  });

  it("merges the server's ranges before editing them, and writes one year bare inside the group", () => {
    const unsorted = {
      ...typed,
      ranges: [
        { lo: 2024, hi: 2024 },
        { lo: 2020, hi: 2023 },
      ],
    };
    const action: SearchAction = {
      type: "yearRemove",
      range: { lo: 2021, hi: 2023 },
      ...yearClauseFromParse(unsorted, source, "native"),
    };
    expect(reduce(at(source), action).q).toBe("trust year:(2020 OR 2024)");
  });

  it("refuses a query ending in an escaping backslash before wrapping it", () => {
    const end: ParsedYearClause = { ...typed, span: [4, 4], ranges: [EVERY_YEAR] };
    const action: SearchAction = {
      type: "yearSet",
      range: { lo: 2020, hi: 2026 },
      ...yearClauseFromParse(end, "foo\\", "native"),
    };
    refused(() => reduce(at("foo\\"), action), "TRAILING_ESCAPE");
  });

  it("refuses an edit over the instance's length limit (TOO_LONG)", () => {
    const action: SearchAction = {
      type: "yearAdd",
      range: { lo: 2022, hi: 2022 },
      ...yearClauseFromParse(typed, source, "native"),
    };
    const limits: QueryLimits = { ...DEFAULT_LIMITS, max_query_length: 24 };
    refused(() => reduce(at(source), action, limits), "TOO_LONG");
    expect(reduce(at(source), action).q).toBe("trust year:(2020 OR 2022)");
  });

  it("formats ranges as the query writes them", () => {
    expect(
      formatYearClause([
        { lo: 2020, hi: 2020 },
        { lo: 2022, hi: 2026 },
      ]),
    ).toBe("year:(2020 OR 2022..2026)");
  });
});

describe("toSearchRequest", () => {
  it("derives offset and limit from page", () => {
    expect(toSearchRequest(at("a", { page: 3, sort: "title" }))).toEqual({
      q: "a",
      mode: "native",
      sort: "title",
      offset: 2 * PAGE_SIZE,
      limit: PAGE_SIZE,
    });
    expect(PAGE_SIZE).toBe(50);
  });
});
