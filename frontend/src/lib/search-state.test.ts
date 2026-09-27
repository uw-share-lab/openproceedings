import { describe, expect, it } from "vitest";
import {
  INITIAL_STATE,
  MAX_PAGE,
  PAGE_SIZE,
  SearchStateError,
  fromURL,
  reduce,
  resultSetKey,
  searchHref,
  toSearchRequest,
  toURL,
  type FilterClause,
  type FilterField,
  type Mode,
  type SearchAction,
  type SearchState,
} from "./search-state";
import golden from "./wrap-golden.json";

const DEFAULT_TRACKS = ["main", "datasets_benchmarks", "position"];

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
        expect(() => reduce(at(c.q), action)).toThrow(/backslash/);
      });
    }
  }
});

describe("facetToggle rewrites q exactly", () => {
  it("on an empty query writes just the clause", () => {
    const next = reduce(at(""), {
      type: "facetToggle",
      field: "track",
      value: "workshop",
      clause: atEnd("track", "", DEFAULT_TRACKS),
    });
    expect(next.q).toBe("track:(main OR datasets_benchmarks OR position OR workshop)");
  });

  it("on a whitespace-only query writes just the clause (never an empty group)", () => {
    const next = reduce(at("   "), {
      type: "facetToggle",
      field: "track",
      value: "workshop",
      clause: atEnd("track", "   ", DEFAULT_TRACKS),
    });
    expect(next.q).toBe("track:(main OR datasets_benchmarks OR position OR workshop)");
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
    expect(next.q).toBe("trust AND track:main AND year:2024");
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
    expect(() =>
      reduce(at("trust"), {
        type: "includeExcluded",
        field: "track",
        value: "main",
        clause: atEnd("track", "trust", DEFAULT_TRACKS),
      }),
    ).toThrow(SearchStateError);
  });
});

describe("filter rewrites refuse what they cannot do exactly", () => {
  it("refuses a clause parsed from a different q", () => {
    expect(() =>
      reduce(at("trust AND llm"), {
        type: "facetToggle",
        field: "track",
        value: "workshop",
        clause: atEnd("track", "trust", DEFAULT_TRACKS),
      }),
    ).toThrow(/different query/);
  });

  it("refuses a clause parsed in the other mode (setMode after the clause was fetched)", () => {
    const fetched = atEnd("track", "trust", DEFAULT_TRACKS, "native");
    const s = reduce(at("trust"), { type: "setMode", mode: "scholar" });
    expect(() =>
      reduce(s, { type: "facetToggle", field: "track", value: "workshop", clause: fetched }),
    ).toThrow(/different query/);
  });

  it("refuses a clause for another field (a status clause passed as track)", () => {
    const q = "trust status:accepted";
    expect(() =>
      reduce(at(q), {
        type: "facetToggle",
        field: "track",
        value: "workshop",
        clause: clause("status", q, [6, 21], ["accepted"]),
      }),
    ).toThrow(/status clause/);
  });

  it("refuses a negated clause: adding to -track:workshop would flip its meaning", () => {
    const q = "trust -track:workshop";
    const negated = { ...clause("track", q, [6, 21], ["workshop"]), negated: true };
    expect(() =>
      reduce(at(q), {
        type: "facetToggle",
        field: "track",
        value: "main",
        // @ts-expect-error a negated clause is not a FilterClause; the runtime check catches untyped callers
        clause: negated,
      }),
    ).toThrow(/negated/);
  });

  it("refuses to remove the last value", () => {
    const q = "trust track:main";
    expect(() =>
      reduce(at(q), {
        type: "facetToggle",
        field: "track",
        value: "main",
        clause: clause("track", q, [6, 16], ["main"]),
      }),
    ).toThrow(/every record/);
  });

  it("refuses a value that is not a bare identifier", () => {
    expect(() =>
      reduce(at("trust"), {
        type: "facetToggle",
        field: "venue",
        value: "ICLR) OR (x",
        clause: atEnd("venue", "trust", ["ICML"]),
      }),
    ).toThrow(/not a venue value/);
  });

  it("refuses a bad value already in the clause's values", () => {
    expect(() =>
      reduce(at("trust"), {
        type: "facetToggle",
        field: "venue",
        value: "ICML",
        clause: atEnd("venue", "trust", ["ICLR OR x"]),
      }),
    ).toThrow(/not a venue value/);
  });

  it("refuses a zero-width span that is not at the end", () => {
    expect(() =>
      reduce(at("trust"), {
        type: "facetToggle",
        field: "track",
        value: "workshop",
        clause: clause("track", "trust", [2, 2], DEFAULT_TRACKS),
      }),
    ).toThrow(/end of q/);
  });

  it("refuses a span outside q", () => {
    expect(() =>
      reduce(at("trust"), {
        type: "facetToggle",
        field: "track",
        value: "workshop",
        clause: clause("track", "trust", [3, 40], ["main"]),
      }),
    ).toThrow(SearchStateError);
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
    expect(() => reduce(at("a"), { type: "page", page: 0 })).toThrow(SearchStateError);
    expect(() => reduce(at("a"), { type: "page", page: 1.5 })).toThrow(SearchStateError);
    expect(() => reduce(at("a"), { type: "page", page: MAX_PAGE + 1 })).toThrow(SearchStateError);
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
