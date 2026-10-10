// @vitest-environment jsdom
import { forEachDiagnostic } from "@codemirror/lint";
import { EditorView } from "@codemirror/view";
import { act, cleanup, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import type { Schemas } from "@/api/client";
import { INITIAL_STATE, searchHref, type ParsedFilters, type SearchState } from "@/lib/search-state";
import {
  json,
  META,
  parsed,
  pass,
  polyfillLayout,
  renderWithApi,
  type Call,
  type Handler,
} from "@/test/api-stub";
import { SearchView } from "./search-view";

const nav = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => nav, usePathname: () => "/search" }));

beforeAll(polyfillLayout);
beforeEach(() => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval", "Date"] });
  nav.push.mockReset();
  nav.replace.mockReset();
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

type Body = Schemas["SearchResponse"];
type Hit = Schemas["Hit"];

const clause = (
  field: "venue" | "track" | "status",
  span: [number, number] | null,
  values: string[] | null,
) => ({
  field,
  negated: false,
  span,
  toggleable: span !== null,
  reason: null,
  blocking_spans: [] as [number, number][],
  values,
});
const year = (span: [number, number], lo = 1000, hi = 9999) => ({
  field: "year" as const,
  negated: false,
  span,
  toggleable: true,
  reason: null,
  blocking_spans: [] as [number, number][],
  ranges: [{ lo, hi }],
});

/** `/parse`'s filters for a query with no filter clause of its own (the backend's report for `trust`). */
function unrestricted(q: string): ParsedFilters {
  const end = [...q].length;
  return {
    venue: clause("venue", [end, end], ["ICLR", "ICML", "NeurIPS"]),
    year: year([end, end]),
    track: clause("track", [end, end], ["datasets_benchmarks", "main", "position"]),
    status: clause("status", [end, end], ["accepted"]),
  };
}

const HIT: Hit = {
  id: "op:iclr:2024:abc",
  title: "Trustworthy LLMs: a 𝔘 benchmark",
  abstract: "We measure trust in models.",
  authors: ["A. Author"],
  venue: "ICLR",
  year: 2024,
  track: "datasets_benchmarks",
  status: "accepted",
  presentation: "poster",
  score: 1.5,
  highlights: { title: [[0, 11]], abstract: [[11, 16]] },
  urls: { forum: "https://openreview.net/forum?id=abc", pdf: null, proceedings: null, doi: "10.1/x" },
  abstract_source: {
    source: "openreview_v2",
    origin: "openreview",
    url: "https://openreview.net/forum?id=abc",
  },
  abstract_withheld: false,
  twins: [],
  abstract_note: null,
};

function body(over: Partial<Body> = {}): Body {
  return {
    query: {
      input: "trust",
      canonical: "trust AND track:(datasets_benchmarks OR main OR position) AND status:accepted",
      canonical_hash: "h",
      identification_query: "trust",
      warnings: [],
      translations: [],
      expansions: {},
    },
    index_version: "a1b2c3d4e5f6",
    tokenizer_version: "t1",
    query_version: "q1",
    total: 412,
    excluded: {
      total: 304,
      track: { workshop: 212, competition: 4, unknown: 0 },
      status: { rejected: 88, unknown: 0 },
    },
    identified_total: 716,
    unclassified_total: 0,
    facets: {
      venue: { NeurIPS: 180, ICLR: 151, ICML: 81 },
      year: { "2024": 141, "2023": 88 },
      track: { main: 301, datasets_benchmarks: 64, position: 47, workshop: 205, competition: 4 },
      status: { accepted: 412, rejected: 88 },
    },
    groups: { counts: [], groups_total: 1, limit: 10, not_counted: "fewer_than_two_groups" },
    hits: [HIT],
    ...over,
  };
}

interface Api {
  search?: (call: Call) => Response | Promise<Response>;
  parse?: (q: string, mode: string) => Response | Promise<Response>;
}

function handler({ search = () => json(body()), parse }: Api = {}): Handler {
  return (call) => {
    if (call.path === "/api/v1/meta") return json(META);
    if (call.path === "/api/v1/search") return search(call);
    if (call.path === "/api/v1/parse") {
      const { q, mode } = call.body as { q: string; mode: string };
      return parse?.(q, mode) ?? json(parsed(q, { filters: unrestricted(q) }));
    }
    return json({ error: { code: "API_NOT_FOUND", message: "no" } }, 404);
  };
}

const stateOf = (over: Partial<SearchState> = {}): SearchState => ({ ...INITIAL_STATE, q: "trust", ...over });

async function setup(state: SearchState = stateOf(), api: Handler = handler()) {
  const r = renderWithApi(<SearchView state={state} />, api);
  await pass(300);
  const view = EditorView.findFromDOM(r.container.querySelector(".cm-editor") as HTMLElement);
  if (view === null) throw new Error("no editor");
  return { ...r, view };
}

const searches = (calls: Call[]) => calls.filter((c) => c.path === "/api/v1/search");
const box = (name: string) => screen.getByRole("checkbox", { name });
const description = (el: HTMLElement) =>
  (el.getAttribute("aria-describedby") ?? "")
    .split(" ")
    .map((id) => document.getElementById(id)?.textContent ?? "")
    .join(" ");

describe("GET /search", () => {
  it("asks for the URL's search, page 1 as offset 0 and 50 per page", async () => {
    const { calls } = await setup(stateOf({ sort: "year_desc", page: 3 }));
    const q = searches(calls)[0]?.query;
    expect(Object.fromEntries(q ?? [])).toEqual({
      q: "trust",
      mode: "native",
      sort: "year_desc",
      offset: "100",
      limit: "50",
    });
  });

  it("says Searching… only after 300 ms while the first answer is in flight (W4)", async () => {
    renderWithApi(
      <SearchView state={stateOf()} />,
      handler({ search: () => new Promise<Response>(() => {}) }),
    );
    await pass(200);
    expect(document.body.textContent).not.toContain("Searching…");
    await pass(150);
    expect(document.body.textContent).toContain("Searching…");
  });

  it("asks nothing for an empty query (the empty state)", async () => {
    const { calls } = await setup(stateOf({ q: "" }));
    expect(searches(calls)).toHaveLength(0);
    expect(screen.queryByRole("region", { name: "Exclusions" })).toBeNull();
  });
});

describe("the builder's expansions come from this /search answer (TASK-111)", () => {
  it("shows the answer's expansions under the group whose wildcard they are", async () => {
    const q = "trust* OR bias";
    const ast: Schemas["ParseResponse"]["ast"] = {
      kind: "or",
      span: [0, 14],
      children: [
        { kind: "wildcard", stem: "trust", op: "*", field: null, span: [0, 6] },
        { kind: "term", token: "bias", field: null, span: [10, 14] },
      ],
    };
    const api = handler({
      search: () =>
        json(body({ query: { ...body().query, input: q, expansions: { "trust*": ["trust", "trusted"] } } })),
      parse: (text) => json(parsed(text, { ast, filters: unrestricted(text) })),
    });
    await setup(stateOf({ q }), api);
    fireEvent.click(screen.getByRole("tab", { name: "Builder" }));
    await pass(10);
    const group = screen.getByRole("group", { name: "Group 1 of 1, any of: trust star, bias" });
    expect(within(group).getByRole("list", { name: "Expansions" }).textContent).toBe(
      "trust* → expands to 2 words: trust, trusted",
    );
  });
});

describe("the builder's group counts come from this /search answer (TASK-176)", () => {
  it("shows the answer's count in each group, beside the answer's total", async () => {
    const q = "trust AND bias";
    const ast: Schemas["ParseResponse"]["ast"] = {
      kind: "and",
      span: [0, 14],
      children: [
        { kind: "term", token: "trust", field: null, span: [0, 5] },
        { kind: "term", token: "bias", field: null, span: [10, 14] },
      ],
    };
    const groups: Body["groups"] = {
      counts: [
        { span: [0, 5], total: 1340, total_without: 977 },
        { span: [10, 14], total: 977, total_without: 1340 },
      ],
      groups_total: 2,
      limit: 10,
      not_counted: null,
    };
    const api = handler({
      search: () => json(body({ query: { ...body().query, input: q }, groups })),
      parse: (text) => json(parsed(text, { ast, filters: unrestricted(text) })),
    });
    await setup(stateOf({ q }), api);
    // outside the Builder tab, a line says where the counts are, and its button opens the tab
    const pointer = "Each of this query's 2 groups has a count in the Builder tab";
    expect(screen.getByText(new RegExp(pointer, "u")).textContent).toBe(
      `${pointer}: how many papers it matches by itself, and how many the query finds without it. Show group counts`,
    );
    fireEvent.click(screen.getByRole("button", { name: "Show group counts" }));
    await pass(10);
    expect(screen.getByRole("tab", { name: "Builder" }).getAttribute("aria-selected")).toBe("true");
    expect(screen.queryByText(new RegExp(pointer, "u"))).toBeNull();
    const first = screen.getByRole("group", { name: "Group 1 of 2, any of: trust" });
    const second = screen.getByRole("group", { name: "Group 2 of 2, any of: bias" });
    expect(within(first).getByText(/this group by itself/u).textContent).toBe(
      "1,340 papers match this group by itself ·; 977 match the query without it (+565)",
    );
    expect(within(second).getByText(/this group by itself/u).textContent).toBe(
      "977 papers match this group by itself ·; 1,340 match the query without it (+928)",
    );
    expect(screen.getByRole("status", { name: "Group counts" }).textContent).toBe(
      "Group counts shown for 2 groups: 412 papers match the whole query.",
    );
  });
});

describe("results header, hits and highlights (W5)", () => {
  it("shows the total, the full index version with Copy, and each hit's API highlights as <mark>", async () => {
    await setup();
    expect(screen.getByText("412 papers")).toBeTruthy();
    expect(screen.getByText("a1b2c3d4e5f6").tagName).toBe("CODE");
    expect(screen.getByRole("button", { name: "Copy index version" })).toBeTruthy();
    const heading = screen.getByRole("heading", { level: 3 });
    const marks = [...document.querySelectorAll("mark")].map((m) => m.textContent);
    expect(marks).toEqual(["Trustworthy", "trust"]);
    expect(heading.querySelector("mark")?.className).toContain("font-bold");
    const link = within(heading).getByRole("link");
    expect(link.getAttribute("href")).toBe("/paper/op%3Aiclr%3A2024%3Aabc?q=trust&mode=native");
    expect(screen.getByRole("heading", { name: "Results, page 1 of 9" })).toBeTruthy();
  });

  it("a Skip to pages link at the top of the results moves focus to the pages", async () => {
    await setup();
    const skip = screen.getByRole("link", { name: "Skip to pages" });
    const results = screen.getByRole("list", { name: "Results" });
    expect(skip.compareDocumentPosition(results) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(skip.className).toContain("focus:not-sr-only"); // shown when it has keyboard focus
    expect(skip.getAttribute("href")).toBe("#results-pages");
    fireEvent.click(skip);
    expect(document.activeElement).toBe(screen.getByRole("navigation", { name: "Pages" }));
  });

  it("draws badges as text (D&B named in full) and only the links the record has", async () => {
    await setup();
    const badges = screen.getByRole("list", { name: "Details" });
    expect(
      within(badges)
        .getAllByRole("listitem")
        .map((li) => li.textContent),
    ).toEqual(["ICLR", "2024", "D&BD&B, datasets and benchmarks", "poster"]);
    const links = screen.getByRole("list", { name: `Links for ${HIT.title}` });
    expect(
      within(links)
        .getAllByRole("link")
        .map((a) => [a.textContent, a.getAttribute("href")]),
    ).toEqual([
      ["OpenReview", "https://openreview.net/forum?id=abc"],
      ["DOI", "https://doi.org/10.1/x"],
    ]);
  });

  it("says when a hit has no abstract, and shows a non-accepted status in words", async () => {
    await setup(
      stateOf(),
      handler({
        search: () =>
          json(
            body({
              hits: [
                { ...HIT, abstract: null, status: "desk_rejected", highlights: { title: [], abstract: [] } },
              ],
            }),
          ),
      }),
    );
    expect(screen.getByText("No abstract in the index")).toBeTruthy();
    expect(screen.getByText("desk rejected, status desk_rejected")).toBeTruthy();
  });

  it("windows a long abstract around its first highlight, with Show full abstract", async () => {
    const abstract = `${"lead ".repeat(200)}trust ${"tail ".repeat(200)}`;
    const at = abstract.indexOf("trust");
    await setup(
      stateOf(),
      handler({
        search: () =>
          json(body({ hits: [{ ...HIT, abstract, highlights: { title: [], abstract: [[at, at + 5]] } }] })),
      }),
    );
    const toggle = screen.getByRole("button", { name: "Show full abstract" });
    const region = document.getElementById(toggle.getAttribute("aria-controls") ?? "");
    expect(region?.textContent?.startsWith("…")).toBe(true);
    expect(region?.textContent?.length).toBeLessThan(abstract.length);
    fireEvent.click(toggle);
    expect(region?.textContent).toBe(abstract);
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
  });
});

describe("exclusion banner (W5, spec 05 §5)", () => {
  it("says what the default filters excluded and itemises the unclassified on their own line", async () => {
    await setup();
    const banner = screen.getByRole("region", { name: "Exclusions" });
    expect(within(banner).getByText("excluded: 212 workshop · 4 competition · 88 rejected")).toBeTruthy();
    expect(within(banner).getByText("unclassified: 0 track unknown · 0 status unknown")).toBeTruthy();
  });

  it("labels each include with the facet count and its accessible name carries that number (M1)", async () => {
    await setup();
    const buttons = within(screen.getByRole("list", { name: "Include excluded papers" })).getAllByRole(
      "button",
    );
    expect(buttons.map((b) => [b.textContent, b.getAttribute("aria-label")])).toEqual([
      ["include 205 workshop ▸", "Include 205 workshop papers"],
      ["include 4 competition ▸", "Include 4 competition papers"],
      ["include 88 rejected ▸", "Include 88 rejected papers"],
    ]);
    expect(description(buttons[0] as HTMLElement)).toContain(
      "the track filter then becomes a limit you wrote",
    );
  });

  it("an include writes the value into q, then moves focus to the count", async () => {
    await setup();
    fireEvent.click(screen.getByRole("button", { name: "Include 205 workshop papers" }));
    expect(nav.push).toHaveBeenCalledWith(
      searchHref(stateOf({ q: "(trust) AND track:(datasets_benchmarks OR main OR position OR workshop)" })),
    );
    expect(document.activeElement?.textContent).toBe("412 papers");
    fireEvent.click(screen.getByRole("button", { name: "Include 88 rejected papers" }));
    expect(nav.push).toHaveBeenLastCalledWith(
      searchHref(stateOf({ q: "(trust) AND status:(accepted OR rejected)" })),
    );
  });

  it("opens the PRISMA disclosure with the default clauses from /parse; Esc closes it", async () => {
    await setup();
    const about = screen.getByRole("button", { name: "About these exclusions" });
    fireEvent.click(about);
    expect(about.getAttribute("aria-expanded")).toBe("true");
    const text = document.getElementById(about.getAttribute("aria-controls") ?? "")?.textContent ?? "";
    expect(text).toContain(
      "The default filters `track:(datasets_benchmarks OR main OR position)` and `status:accepted` removed 304 records before screening.",
    );
    fireEvent.keyDown(screen.getByRole("button", { name: "Close" }), { key: "Escape" });
    expect(about.getAttribute("aria-expanded")).toBe("false");
    expect(document.activeElement).toBe(about);
  });

  it("announces what an include did and the new total once its search lands", async () => {
    const r = await setup(
      stateOf(),
      handler({
        search: (call) =>
          json(
            call.query.get("q") === "trust"
              ? body()
              : body({
                  total: 617,
                  excluded: {
                    total: 99,
                    track: { competition: 4, unknown: 0 },
                    status: { rejected: 95, unknown: 0 },
                  },
                }),
          ),
      }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Include 205 workshop papers" }));
    const next = stateOf({ q: "(trust) AND track:(datasets_benchmarks OR main OR position OR workshop)" });
    r.rerender(<SearchView state={next} />);
    await pass(300);
    expect(screen.getByText("Track: workshop included. 617 papers.")).toBeTruthy();
  });
});

describe("Limits you wrote", () => {
  it("reads none for a query whose filters are all defaults", async () => {
    await setup();
    expect(screen.getByText("Limits you wrote:").parentElement?.textContent).toBe("Limits you wrote: none");
  });

  it("lists a written clause as its text and what it leaves out, and the banner names the limit (M2)", async () => {
    const q = "trust track:(main OR workshop)";
    await setup(
      stateOf({ q }),
      handler({
        parse: (text) =>
          json(
            parsed(text, {
              defaults: ["status"],
              filters: { ...unrestricted(text), track: clause("track", [6, 30], ["main", "workshop"]) },
            }),
          ),
        search: () =>
          json(
            body({ excluded: { total: 88, track: { unknown: 0 }, status: { rejected: 88, unknown: 0 } } }),
          ),
      }),
    );
    expect(screen.getByText("Limits you wrote:").parentElement?.textContent).toBe(
      "Limits you wrote: track:(main OR workshop) — leaves out 64 datasets_benchmarks · 47 position · 4 competition",
    );
    expect(
      screen.getByText("excluded: 88 rejected · track: your limit applies (see Limits you wrote)"),
    ).toBeTruthy();
    expect(screen.getByText("unclassified: 0 status unknown")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Filters (1 active)" })).toBeTruthy();
  });
});

describe("filter sidebar (spec 05 §4; W13)", () => {
  it("labels each option with its facet count; checked = the clause admits it; (default) on track and status", async () => {
    await setup();
    expect(box("workshop, 205 papers")).toHaveProperty("checked", false);
    expect(box("main, 301 papers")).toHaveProperty("checked", true);
    expect(box("D&B, datasets and benchmarks, 64 papers")).toHaveProperty("checked", true);
    expect(box("ICML, 81 papers")).toHaveProperty("checked", true);
    expect(screen.getByText("All venues: untick one to leave it out.")).toBeTruthy();
    const track = screen.getByRole("group", { name: "Track (default)" });
    expect(track).toBeTruthy();
    expect(screen.getByRole("group", { name: "Venue" })).toBeTruthy();
  });

  it("a toggle rewrites q through the reducer and pushes it", async () => {
    await setup();
    fireEvent.click(box("workshop, 205 papers"));
    expect(nav.push).toHaveBeenCalledWith(
      searchHref(stateOf({ q: "(trust) AND track:(datasets_benchmarks OR main OR position OR workshop)" })),
    );
    fireEvent.click(box("ICML, 81 papers"));
    expect(nav.push).toHaveBeenLastCalledWith(
      searchHref(stateOf({ q: "(trust) AND venue:(ICLR OR NeurIPS)" })),
    );
  });

  it("unticking the last value is disabled with the reducer's reason on that checkbox (LAST_VALUE)", async () => {
    await setup();
    const accepted = box("accepted, 412 papers");
    expect(accepted.getAttribute("aria-disabled")).toBe("true");
    expect(description(accepted)).toContain("Removing the last status value would exclude every record");
    fireEvent.click(accepted);
    expect(nav.push).not.toHaveBeenCalled();
  });

  it("disables every filter with DRAFT_DIRTY while the editor has unsearched edits (SB-6)", async () => {
    const { view } = await setup();
    act(() => {
      view.dispatch({ changes: { from: view.state.doc.length, insert: " x" } });
    });
    await pass(300);
    const workshop = box("workshop, 205 papers");
    expect(workshop.getAttribute("aria-disabled")).toBe("true");
    expect(description(workshop)).toContain("The editor has changes you haven't searched");
    const include = screen.getByRole("button", { name: "Include 205 workshop papers" });
    expect(include.getAttribute("aria-disabled")).toBe("true");
    fireEvent.click(workshop);
    fireEvent.click(include);
    expect(nav.push).not.toHaveBeenCalled();
  });

  it("while /parse hasn't answered, controls are aria-disabled, and the reason appears only after 500 ms", async () => {
    await setup(stateOf(), handler({ parse: () => new Promise<Response>(() => {}) }));
    const workshop = box("workshop, 205 papers");
    expect(workshop.getAttribute("aria-disabled")).toBe("true");
    expect(document.body.textContent).not.toContain("was read from an earlier query");
    await pass(300);
    expect(document.body.textContent).toContain(
      "The track filter was read from an earlier query — the query or mode changed after it was parsed.",
    );
  });

  it("names why a field can't be edited and offers Show the clauses, which selects the first (multiple_clauses)", async () => {
    const q = "trust track:main (track:workshop x)";
    const { view } = await setup(
      stateOf({ q }),
      handler({
        parse: (text) =>
          json(
            parsed(text, {
              defaults: ["status"],
              filters: {
                ...unrestricted(text),
                track: {
                  ...clause("track", null, null),
                  reason: "multiple_clauses",
                  blocking_spans: [
                    [6, 16],
                    [18, 32],
                  ],
                },
              },
            }),
          ),
      }),
    );
    const track = screen.getByRole("group", { name: "Track" });
    expect(track.textContent).toContain(
      "The track filter cannot be changed here — the query has more than one top-level track: clause.",
    );
    // the reducer's `backticked` query text is drawn as code, not with its backticks
    expect(within(track).getByText("track:").tagName).toBe("CODE");
    const main = within(track).getByRole("checkbox", { name: "main, 301 papers" });
    expect(main.getAttribute("aria-disabled")).toBe("true");
    expect((main as HTMLInputElement).indeterminate).toBe(true);
    fireEvent.click(within(track).getByRole("button", { name: "Show the clauses in the editor" }));
    const sel = view.state.selection.main;
    expect(view.state.sliceDoc(sel.from, sel.to)).toBe("track:main");
  });

  it("with no search that ever ran, a 422 says the query wasn't searched instead of an empty list (ER-2)", async () => {
    await setup(
      stateOf({ q: "(trust" }),
      handler({
        parse: (text) =>
          json(
            parsed(text, {
              errors: [{ code: "PARSE_UNBALANCED_PAREN", message: "m", span: [0, 1], reading: null }],
            }),
          ),
        search: () => json({ error: { code: "PARSE_UNBALANCED_PAREN", message: "m", diagnostics: [] } }, 422),
      }),
    );
    expect(
      screen.getByText("No results: the query has 1 error. Fix it above and search again."),
    ).toBeTruthy();
  });
});

describe("year (TASK-092 actions)", () => {
  it("lists years newest first; unticking one removes it from every year", async () => {
    await setup();
    const years = within(screen.getByRole("group", { name: "Year" })).getAllByRole("checkbox");
    expect(years.map((y) => y.getAttribute("aria-label") ?? y.parentElement?.textContent)).toEqual([
      "2024, 141 papers",
      "2023, 88 papers",
    ]);
    fireEvent.click(box("2023, 88 papers"));
    expect(nav.push).toHaveBeenCalledWith(
      searchHref(stateOf({ q: "(trust) AND year:(1000..2022 OR 2024..9999)" })),
    );
  });

  it("sets a from–to range, and All years is disabled with the reason when every year is admitted", async () => {
    await setup();
    const group = screen.getByRole("group", { name: "Year" });
    const all = within(group).getByRole("button", { name: "All years" });
    expect(all.getAttribute("aria-disabled")).toBe("true");
    expect(description(all)).toContain("Every year is already included");
    expect(within(group).getByText("Every year.")).toBeTruthy();
    expect((within(group).getByRole("textbox", { name: "From year" }) as HTMLInputElement).value).toBe(
      "2023",
    );
    fireEvent.change(within(group).getByRole("textbox", { name: "To year" }), { target: { value: "2026" } });
    fireEvent.click(within(group).getByRole("button", { name: "Set years" }));
    expect(nav.push).toHaveBeenCalledWith(searchHref(stateOf({ q: "(trust) AND year:(2023..2026)" })));
    fireEvent.change(within(group).getByRole("textbox", { name: "To year" }), { target: { value: "20x" } });
    const set = within(group).getByRole("button", { name: "Set years" });
    expect(set.getAttribute("aria-disabled")).toBe("true");
    expect(description(set)).toBe("Type a four-digit year in both boxes, the earlier first.");
  });

  it("edits a written year clause in place, and All years rewrites it", async () => {
    const q = "trust year:2020..2022";
    const { view } = await setup(
      stateOf({ q }),
      handler({
        parse: (text) =>
          json(parsed(text, { filters: { ...unrestricted(text), year: year([6, 21], 2020, 2022) } })),
      }),
    );
    expect(
      within(screen.getByRole("group", { name: "Year" })).getByText("Includes 2020..2022."),
    ).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "All years" }));
    expect(nav.push).toHaveBeenCalledWith(searchHref(stateOf({ q: "trust year:(1000..9999)" })));
    fireEvent.click(screen.getByRole("button", { name: /Edit year: in the query/ }));
    const sel = view.state.selection.main;
    expect(view.state.sliceDoc(sel.from, sel.to)).toBe("year:2020..2022");
  });

  it("Edit year: with no year clause adds one to the draft with its range selected (S14)", async () => {
    const { view } = await setup();
    fireEvent.click(screen.getByRole("button", { name: /Edit year: in the query/ }));
    await pass(0);
    expect(view.state.doc.toString()).toBe("trust year:2020..2026");
    const sel = view.state.selection.main;
    expect(view.state.sliceDoc(sel.from, sel.to)).toBe("2020..2026");
    expect(nav.push).not.toHaveBeenCalled();
  });
});

describe("sort and paging", () => {
  it("a sort pushes the same q with the new order and page 1", async () => {
    await setup(stateOf({ page: 2 }));
    fireEvent.change(screen.getByRole("combobox", { name: "Sort" }), { target: { value: "year_desc" } });
    expect(nav.push).toHaveBeenCalledWith("/search?q=trust&mode=native&sort=year_desc");
  });

  it("Next replaces the URL (Back leaves the search) and focus goes to the results heading", async () => {
    const r = await setup(stateOf(), handler({ search: () => json(body({ total: 120 })) }));
    const pages = screen.getByRole("navigation", { name: "Pages" });
    expect(within(pages).getByText("Page 1 of 3")).toBeTruthy();
    expect(within(pages).getByRole("button", { name: "Previous" }).getAttribute("aria-disabled")).toBe(
      "true",
    );
    fireEvent.click(within(pages).getByRole("button", { name: "Next" }));
    expect(nav.replace).toHaveBeenCalledWith("/search?q=trust&mode=native&page=2");
    expect(nav.push).not.toHaveBeenCalled();
    r.rerender(<SearchView state={stateOf({ page: 2 })} />);
    await pass(0);
    expect(document.activeElement?.textContent).toMatch(/^Results, page/);
  });

  it("Go to page refuses a page out of range with a reason, and jumps to one in range", async () => {
    await setup(stateOf(), handler({ search: () => json(body({ total: 120 })) }));
    const input = screen.getByRole("textbox", { name: "Go to page" });
    fireEvent.change(input, { target: { value: "9" } });
    fireEvent.submit(input);
    expect(
      screen.getByText("Page 9 is past the last page — this search has 3 pages. Choose a page from 1 to 3."),
    ).toBeTruthy();
    fireEvent.change(input, { target: { value: "x" } });
    fireEvent.submit(input);
    expect(
      screen.getByText(
        '"x" is not a page number — a page is a whole number from 1 to 10,000. Choose a page in that range.',
      ),
    ).toBeTruthy();
    fireEvent.change(input, { target: { value: "3" } });
    fireEvent.submit(input);
    expect(nav.replace).toHaveBeenCalledWith("/search?q=trust&mode=native&page=3");
  });
});

describe("zero results (W8)", () => {
  it("says what matched nothing, what was excluded, and opens How we read your query", async () => {
    await setup(
      stateOf(),
      handler({
        search: () =>
          json(
            body({
              total: 0,
              hits: [],
              excluded: { total: 3, track: { workshop: 3, unknown: 0 }, status: { unknown: 0 } },
            }),
          ),
      }),
    );
    expect(screen.getByText("0 papers match")).toBeTruthy();
    const text = document.body.textContent ?? "";
    expect(text).toContain(
      "0 papers match trust AND track:(datasets_benchmarks OR main OR position) AND status:accepted. 3 were excluded by the default filters above.",
    );
    expect(text).toContain("Words match exactly: benchmarks doesn't find benchmark; benchmark$ finds both.");
    expect(screen.getByRole("button", { name: /How we read your query/ }).getAttribute("aria-expanded")).toBe(
      "true",
    );
    expect(screen.queryByRole("navigation", { name: "Pages" })).toBeNull();
  });
});

describe("refusals and failures (W6, W9, W10, W12)", () => {
  it("a 422 draws its diagnostics on the editor and keeps the last good search, marked stale, with Restore it", async () => {
    const bad = "trust (";
    const r = await setup(
      stateOf(),
      handler({
        search: (call) =>
          call.query.get("q") === bad
            ? json(
                {
                  error: {
                    code: "PARSE_UNBALANCED_PAREN",
                    message: "no )",
                    diagnostics: [
                      {
                        code: "PARSE_UNBALANCED_PAREN",
                        message: "`(` has no closing parenthesis",
                        span: [6, 7],
                      },
                    ],
                  },
                },
                422,
              )
            : json(body()),
        parse: (text) =>
          json(
            text === bad
              ? parsed(text, {
                  errors: [{ code: "PARSE_UNBALANCED_PAREN", message: "m", span: [6, 7], reading: null }],
                })
              : parsed(text, { filters: unrestricted(text) }),
          ),
      }),
    );
    r.rerender(<SearchView state={stateOf({ q: bad })} />);
    await pass(300);
    const squiggles: [number, number][] = [];
    forEachDiagnostic(r.view.state, (_d, from, to) => squiggles.push([from, to]));
    expect(squiggles).toEqual([[6, 7]]);
    expect(screen.getByText("Showing the last search that ran, not the query above")).toBeTruthy();
    expect(screen.getByText("412 papers")).toBeTruthy();
    expect(screen.getByText("Filters are unavailable until the query parses.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Restore it" }));
    expect(nav.push).toHaveBeenCalledWith("/search?q=trust&mode=native");
  });

  it("a 429 shows the server's message and a countdown; Retry is enabled at 0 and asks again", async () => {
    let n = 0;
    const { calls } = await setup(
      stateOf(),
      handler({
        search: () =>
          n++ === 0
            ? json(
                { error: { code: "API_RATE_LIMITED", message: "Too many requests; try again in 3 s." } },
                429,
                {
                  "Retry-After": "3",
                },
              )
            : json(body()),
      }),
    );
    expect(screen.getByRole("heading", { name: "The search didn't run" })).toBeTruthy();
    expect(screen.getByText("Too many requests; try again in 3 s.")).toBeTruthy();
    expect(screen.getByText("Retry in 3 s")).toBeTruthy();
    const retry = screen.getByRole("button", { name: "Retry" });
    expect(retry.getAttribute("aria-disabled")).toBe("true");
    fireEvent.click(retry);
    expect(searches(calls)).toHaveLength(1);
    for (let s = 0; s < 3; s++) await pass(1000);
    expect(screen.getByText("You can retry now")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await pass(0);
    expect(searches(calls)).toHaveLength(2);
    expect(screen.getByText("412 papers")).toBeTruthy();
  });

  it.each([
    [
      503,
      { error: { code: "API_INDEX_NOT_LOADED", message: "No index is loaded yet." } },
      "Search index loading",
    ],
    [500, { error: { code: "API_INTERNAL", message: "boom" } }, "Something went wrong on the server"],
    [502, "<html>bad gateway</html>", "The server didn't answer"],
  ])("HTTP %i shows its own state, never blamed on the query", async (status, answer, heading) => {
    await setup(
      stateOf(),
      handler({
        search: () =>
          typeof answer === "string"
            ? new Response(answer, { status, headers: { "Content-Type": "text/html" } })
            : json(answer, status),
      }),
    );
    expect(screen.getByRole("heading", { name: heading })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
    if (status === 500) {
      const report = screen.getByRole("link", { name: /Report it/ }).getAttribute("href") ?? "";
      expect(report).toContain("API_INTERNAL");
      expect(report).not.toContain("trust");
    }
    if (status === 502)
      expect(document.body.textContent).toContain("(HTTP 502, not from the search service)");
  });

  it("names both index versions when the index changed under the same query", async () => {
    const r = await setup(
      stateOf(),
      handler({
        search: (call) =>
          json(body({ index_version: call.query.get("offset") === "0" ? "a1b2c3d4e5f6" : "9f8e7d6c5b4a" })),
      }),
    );
    r.rerender(<SearchView state={stateOf({ page: 2 })} />);
    await pass(0);
    const notice = screen.getByText(/The index changed while you were working/);
    expect(notice.textContent).toContain(
      "results are now from index 9f8e7d6c5b4a (they were from a1b2c3d4e5f6)",
    );
    fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(screen.queryByText(/The index changed while you were working/)).toBeNull();
  });
});

describe("Export and Save in the results header (TASK-044)", () => {
  /** `/parse` for `q` with a written status clause admitting rejected (so the status warning shows). */
  function withStatus(q: string): ParsedFilters {
    const n = [...q].length;
    return { ...unrestricted(q), status: clause("status", [n - 29, n], ["accepted", "rejected"]) };
  }
  const Q = "trust AND status:(accepted OR rejected)";
  const withWarning = () =>
    handler({ parse: (q) => json(parsed(q, { filters: withStatus(q), defaults: ["track"] })) });

  it("pins the export to the shown search and warns about the non-accepted papers it holds", async () => {
    await setup(stateOf({ q: Q }), withWarning());
    const exportButton = screen.getByRole("button", { name: "Export 412 papers" });
    expect(exportButton.getAttribute("aria-disabled")).toBeNull();
    expect(screen.getByRole("button", { name: /Includes 88 rejected papers/ })).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Save search record" }).getAttribute("aria-disabled"),
    ).toBeNull();
  });

  it("Show the Status filter moves focus to the sidebar's Status field", async () => {
    await setup(stateOf({ q: Q }), withWarning());
    fireEvent.click(screen.getByRole("button", { name: "Export 412 papers" }));
    fireEvent.click(screen.getByRole("button", { name: "Show the Status filter" }));
    await pass(0);
    expect(document.activeElement?.tagName).toBe("FIELDSET");
    expect(document.activeElement?.querySelector("legend")?.textContent).toContain("Status");
  });

  it("disables both with DRAFT_DIRTY while the editor has unsearched edits", async () => {
    const { view } = await setup();
    act(() => {
      view.dispatch({ changes: { from: view.state.doc.length, insert: " x" } });
    });
    await pass(300);
    for (const name of ["Export 412 papers", "Save search record"]) {
      const b = screen.getByRole("button", { name });
      expect(b.getAttribute("aria-disabled")).toBe("true");
      expect(description(b)).toContain("The editor has changes you haven't searched");
    }
  });
});
