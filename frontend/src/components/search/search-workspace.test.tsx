// @vitest-environment jsdom
import { forEachDiagnostic } from "@codemirror/lint";
import { EditorView } from "@codemirror/view";
import { act, cleanup, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import type { Schemas } from "@/api/client";
import { INITIAL_STATE, type SearchState } from "@/lib/search-state";
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
import coverageFixture from "@/components/coverage/coverage-fixture.json";
import { REVIEW_EXAMPLE } from "./examples";
import { SearchWorkspace, type SearchRefusal } from "./search-workspace";

const nav = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => nav, usePathname: () => "/search" }));

beforeAll(polyfillLayout);
beforeEach(() => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval", "Date"] });
  nav.push.mockReset();
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

type Diag = Schemas["Diagnostic"];
const diag = (
  code: Diag["code"],
  message: string,
  span: [number, number] | null,
  reading: string | null = null,
): Diag => ({ code, message, span, reading });

const parseCalls = (calls: Call[]) => calls.filter((c) => c.path === "/api/v1/parse");

/** /meta and /coverage (the API's own coverage fixture) answer; /parse answers from `parse` (by default: parsed, no diagnostics). */
function api(
  parse: (q: string, mode: string, call: Call) => Response | Promise<Response> = (q) => json(parsed(q)),
): Handler {
  return (call) => {
    if (call.path === "/api/v1/meta") return json(META);
    if (call.path === "/api/v1/coverage") return json(coverageFixture);
    if (call.path === "/api/v1/parse") {
      const body = call.body as { q: string; mode: string };
      return parse(body.q, body.mode, call);
    }
    return json({ error: { code: "API_NOT_FOUND", message: "no" } }, 404);
  };
}

function setup(
  state: Partial<SearchState> = {},
  handler: Handler = api(),
  refusal: SearchRefusal | null = null,
) {
  const r = renderWithApi(
    <SearchWorkspace state={{ ...INITIAL_STATE, ...state }} refusal={refusal} />,
    handler,
  );
  const view = EditorView.findFromDOM(r.container.querySelector(".cm-editor") as HTMLElement);
  if (view === null) throw new Error("no editor");
  const type = (text: string) =>
    act(() => {
      view.dispatch({
        changes: { from: 0, to: view.state.doc.length, insert: text },
        selection: { anchor: text.length },
      });
    });
  const squiggles = () => {
    const out: [number, number, string, string][] = [];
    forEachDiagnostic(view.state, (d, from, to) => out.push([from, to, d.severity, d.message]));
    return out;
  };
  const summary = () => screen.getByRole("status", { name: "" }).textContent;
  return { ...r, view, type, squiggles, summary };
}

/** The summary live region (the editor's description). */
function summaryOf(view: EditorView): HTMLElement {
  const id = view.contentDOM.getAttribute("aria-describedby") ?? "";
  const el = document.getElementById(id);
  if (el === null) throw new Error("no summary");
  return el;
}

describe("the editor's accessible contract", () => {
  it("is named Query, described by a polite live summary, and never traps Tab", async () => {
    const { view } = setup({ q: "trust", mode: "native" });
    await pass(300);
    expect(view.contentDOM.getAttribute("aria-label")).toBe("Query");
    expect(view.contentDOM.getAttribute("role")).toBe("textbox");
    const summary = summaryOf(view);
    expect(summary.getAttribute("role")).toBe("status");
    expect(summary.getAttribute("aria-live")).toBe("polite");
    // Tab is not bound, so the browser moves focus on (no indentWithTab)
    const tab = new KeyboardEvent("keydown", { key: "Tab", bubbles: true, cancelable: true });
    view.contentDOM.dispatchEvent(tab);
    expect(tab.defaultPrevented).toBe(false);
  });

  it("puts the Syntax select, the editor and Search in one search landmark", () => {
    setup();
    const form = screen.getByRole("search", { name: "Query" });
    expect(within(form).getByRole("combobox", { name: "Syntax" })).toBeTruthy();
    expect(within(form).getByRole("textbox", { name: "Query" })).toBeTruthy();
    expect(within(form).getByRole("button", { name: "Search" })).toBeTruthy();
  });
});

describe("debounced POST /parse", () => {
  it("asks once, 250 ms after the last keystroke, with the draft's text and mode", async () => {
    const { type, calls } = setup();
    await type("t");
    await pass(100);
    await type("tr");
    await pass(100);
    await type("trust");
    await pass(249);
    expect(parseCalls(calls)).toHaveLength(0);
    await pass(1);
    expect(parseCalls(calls).map((c) => c.body)).toEqual([{ q: "trust", mode: "native" }]);
  });

  it("doesn't ask about an empty editor", async () => {
    const { calls } = setup();
    await pass(1000);
    expect(parseCalls(calls)).toHaveLength(0);
  });

  it("cancels the older request and never shows its late answer for the newer draft", async () => {
    let releaseFirst: (r: Response) => void = () => {};
    const handler = api((q) => {
      if (q === "trust or") return new Promise<Response>((resolve) => (releaseFirst = resolve));
      return json(parsed(q));
    });
    const { type, calls, view } = setup({}, handler);
    await type("trust or");
    await pass(250);
    await type("trust OR x");
    await pass(250);
    const [first, second] = parseCalls(calls);
    expect(first?.signal.aborted).toBe(true);
    expect(second?.signal.aborted).toBe(false);
    releaseFirst(
      json(
        parsed("trust or", {
          warnings: [diag("WARN_LOWERCASE_OPERATOR", "`or` is searched as a word", [6, 8])],
        }),
      ),
    );
    await pass(10);
    expect(screen.queryByText(/is searched as a word/)).toBeNull();
    expect(summaryOf(view).textContent).toBe("not searched yet");
  });
});

describe("squiggles from the server's code-point spans", () => {
  it("are drawn at the UTF-16 positions after an astral character, with the server's message", async () => {
    // `𝐱` is one code point and two UTF-16 units: the wildcard `ab*` is code points [2, 5), units [3, 6)
    const handler = api((q) =>
      json({
        ...parsed(q),
        ast: null,
        effective_ast: null,
        canonical: null,
        errors: [diag("WILDCARD_STEM_TOO_SHORT", "The wildcard `ab*` keeps fewer than 3 letters", [2, 5])],
        warnings: [diag("WARN_CJK_RUN", "cjk", [0, 1])],
        translations: [diag("COMPAT_POP_DOLLAR", "read as", [5, 5])],
      }),
    );
    const { type, squiggles } = setup({}, handler);
    await type("𝐱 ab*");
    await pass(300);
    expect(squiggles()).toEqual([
      [0, 2, "warning", "cjk"],
      [3, 6, "error", "The wildcard `ab*` keeps fewer than 3 letters"],
      [5, 6, "info", "read as"], // a zero-width span at the end is widened back over the last code point
    ]);
  });

  it("F8 and Shift-F8 move the cursor to the next and previous diagnostic", async () => {
    const handler = api((q) =>
      json({
        ...parsed(q),
        warnings: [
          diag("WARN_LOWERCASE_OPERATOR", "or", [2, 4]),
          diag("WARN_LOWERCASE_OPERATOR", "and", [7, 10]),
        ],
      }),
    );
    const { type, view } = setup({}, handler);
    await type("a or b and c");
    await pass(300);
    act(() => view.dispatch({ selection: { anchor: 0 } }));
    fireEvent.keyDown(view.contentDOM, { key: "F8" });
    expect([view.state.selection.main.from, view.state.selection.main.to]).toEqual([2, 4]);
    fireEvent.keyDown(view.contentDOM, { key: "F8" });
    expect([view.state.selection.main.from, view.state.selection.main.to]).toEqual([7, 10]);
    fireEvent.keyDown(view.contentDOM, { key: "F8", shiftKey: true });
    expect([view.state.selection.main.from, view.state.selection.main.to]).toEqual([2, 4]);
  });

  it("are not drawn on a text they weren't reported for", async () => {
    let release: (r: Response) => void = () => {};
    const handler = api(
      (q) =>
        new Promise<Response>(
          (resolve) =>
            (release = () =>
              resolve(json(parsed(q, { errors: [diag("PARSE_EXPECTED_TERM", "x", [0, 1])] })))),
        ),
    );
    const { type, squiggles } = setup({}, handler);
    await type("a OR");
    await pass(250);
    await type("a OR b"); // typed before the answer lands; the new request is still pending
    release(json({}));
    await pass(10);
    expect(squiggles()).toEqual([]);
  });
});

describe("the diagnostics row", () => {
  const mixed =
    "AND binds tighter than OR, so this is read as `a OR (b AND c)` — add parentheses if you meant something else.";

  it("lists errors, then translations, then warnings, verbatim, with Help links and screen-reader prefixes", async () => {
    const handler = api((q) =>
      json({
        ...parsed(q),
        errors: [diag("PARSE_UNBALANCED_PAREN", "This `(` is never closed — add a `)`.", [0, 1])],
        warnings: [diag("WARN_LOWERCASE_OPERATOR", "`or` is searched as a word", [3, 5])],
        translations: [diag("COMPAT_SOURCE_ALIAS", "`source:ICLR` is read as `venue:ICLR`.", [6, 17])],
      }),
    );
    const { type } = setup({}, handler);
    await type("(a or source:ICLR");
    await pass(300);
    const row = screen.getByRole("region", { name: "Diagnostics" });
    const lists = within(row)
      .getAllByRole("list")
      .map((l) => l.getAttribute("aria-label"));
    expect(lists).toEqual(["Errors", "Translations", "Warnings"]);
    const error = within(within(row).getByRole("list", { name: "Errors" })).getByRole("listitem");
    expect(error.textContent).toContain("Error: This `(` is never closed — add a `)`.");
    const help = within(error).getByRole("link", { name: "Syntax help for PARSE_UNBALANCED_PAREN" });
    expect(help.getAttribute("href")).toBe("/help/syntax#parse_unbalanced_paren");
    expect(within(row).getByText("Read as native syntax:")).toBeTruthy();
  });

  it("collapses a repeated code into one line with its count, expandable to every message", async () => {
    const handler = api((q) =>
      json({
        ...parsed(q),
        warnings: [0, 2, 4].map((k) => diag("WARN_SPELLED_GREEK", `greek ${k}`, [k, k + 1])),
      }),
    );
    const { type } = setup({}, handler);
    await type("a b c");
    await pass(300);
    const list = screen.getByRole("list", { name: "Warnings" });
    const line = within(list).getAllByRole("listitem")[0]!;
    expect(line.textContent).toMatch(/^⚠Warning: 3 × greek 0/);
    const all = within(line).getByRole("button", { name: "Show all 3" });
    expect(all.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(all);
    expect(within(line).getByText("greek 4")).toBeTruthy();
  });

  it("opens the tree for mixed AND/OR, and Show how it was read moves focus to it", async () => {
    const handler = api((q) => json({ ...parsed(q), warnings: [diag("WARN_MIXED_AND_OR", mixed, [0, 13])] }));
    const { type } = setup({}, handler);
    await type("a OR b AND c");
    await pass(300);
    const tree = screen.getByRole("button", { name: /How we read your query/ });
    expect(tree.getAttribute("aria-expanded")).toBe("true");
    fireEvent.click(tree);
    expect(tree.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(screen.getByRole("button", { name: "Show how it was read" }));
    expect(tree.getAttribute("aria-expanded")).toBe("true");
    expect(document.activeElement).toBe(tree);
  });

  it("Load with parentheses puts the server's reading into the editor as a draft, without searching", async () => {
    // the reading comes from the `reading` field (TASK-099), never from the message, which here quotes none
    const warning = diag("WARN_MIXED_AND_OR", "AND binds tighter than OR.", [0, 12], "a OR (b AND c)");
    const handler = api((q) => json({ ...parsed(q), warnings: [warning] }));
    const { type, view, calls } = setup({}, handler);
    await type("a OR b AND c");
    await pass(300);
    fireEvent.click(screen.getByRole("button", { name: "Load with parentheses" }));
    expect(view.state.doc.toString()).toBe("a OR (b AND c)");
    expect(nav.push).not.toHaveBeenCalled();
    await pass(300);
    expect(parseCalls(calls).at(-1)?.body).toEqual({ q: "a OR (b AND c)", mode: "native" });
  });

  it("offers no Load with parentheses for a mixed AND/OR warning without a reading", async () => {
    const handler = api((q) => json({ ...parsed(q), warnings: [diag("WARN_MIXED_AND_OR", mixed, [0, 12])] }));
    const { type } = setup({}, handler);
    await type("a OR b AND c");
    await pass(300);
    expect(screen.getByRole("button", { name: "Show how it was read" })).toBeTruthy(); // the tree renders
    expect(screen.getByRole("button", { name: /How we read your query/ })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Load with parentheses" })).toBeNull();
  });

  it("offers no Show how it was read when the query has errors, since there is no tree to open", async () => {
    // TASK-140: a mixed level with errors has no reading, and the parse has no effective_ast, so no tree renders
    const warning = diag(
      "WARN_MIXED_AND_OR",
      "`a b OR () OR c` mixes AND and OR without parentheses",
      [0, 14],
    );
    const handler = api((q) =>
      json({
        ...parsed(q),
        ast: null,
        effective_ast: null,
        canonical: null,
        canonical_hash: null,
        identification_query: null,
        errors: [diag("PARSE_EMPTY_GROUP", "`()` is an empty group", [7, 9])],
        warnings: [warning],
      }),
    );
    const { type } = setup({}, handler);
    await type("a b OR () OR c");
    await pass(300);
    expect(within(screen.getByRole("list", { name: "Warnings" })).getByText(/mixes AND and OR/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Show how it was read" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Load with parentheses" })).toBeNull();
    expect(screen.queryByRole("button", { name: /How we read your query/ })).toBeNull();
  });

  it("offers Read as Google Scholar syntax for FIELD_COMPAT_ONLY: it sets the select and keeps the text", async () => {
    const handler = api((q, mode) =>
      json(
        mode === "native"
          ? {
              ...parsed(q),
              errors: [diag("FIELD_COMPAT_ONLY", "`source:` is Google Scholar syntax", [0, 7])],
            }
          : parsed(q, { mode: "scholar" }),
      ),
    );
    const { type, view, calls } = setup({}, handler);
    await type("source:ICLR");
    await pass(300);
    fireEvent.click(screen.getByRole("button", { name: "Read as Google Scholar syntax" }));
    expect((screen.getByRole("combobox", { name: "Syntax" }) as HTMLSelectElement).value).toBe("scholar");
    expect(view.state.doc.toString()).toBe("source:ICLR");
    await pass(300);
    expect(parseCalls(calls).at(-1)?.body).toEqual({ q: "source:ICLR", mode: "scholar" });
    expect(screen.queryByRole("button", { name: "Read as Google Scholar syntax" })).toBeNull();
  });
});

describe("the draft is (text, mode): DRAFT_DIRTY", () => {
  it("clean: the summary counts only; dirty: 'not searched yet', and Revert edits restores q", async () => {
    const handler = api((q) => json({ ...parsed(q), warnings: [diag("WARN_CJK_RUN", "cjk", [0, 1])] }));
    const { type, view } = setup({ q: "trust", mode: "native" }, handler);
    await pass(300);
    expect(summaryOf(view).textContent).toBe("1 warning");
    expect(screen.queryByRole("button", { name: "Revert edits" })).toBeNull();
    await type("trust AND x");
    await pass(300);
    expect(summaryOf(view).textContent).toBe("1 warning — not searched yet");
    expect(screen.getByRole("heading", { name: "Draft — not searched" })).toBeTruthy();
    const revert = screen.getByRole("button", { name: "Revert edits" });
    expect(revert.getAttribute("aria-describedby")).toBeTruthy();
    fireEvent.click(revert);
    expect(view.state.doc.toString()).toBe("trust");
  });

  it("a Syntax change alone makes the draft dirty", async () => {
    const { view, calls } = setup({ q: "trust", mode: "native" });
    await pass(300);
    fireEvent.change(screen.getByRole("combobox", { name: "Syntax" }), { target: { value: "scholar" } });
    await pass(300);
    expect(summaryOf(view).textContent).toBe("syntax changed — not searched yet");
    expect(parseCalls(calls).at(-1)?.body).toEqual({ q: "trust", mode: "scholar" });
    expect(screen.getByRole("button", { name: "Revert edits" })).toBeTruthy();
  });

  it("keeps the searched query's warnings one click away while the draft is dirty", async () => {
    const handler = api((q) =>
      json(
        q === "a or b"
          ? { ...parsed(q), warnings: [diag("WARN_LOWERCASE_OPERATOR", "or is a word", [2, 4])] }
          : parsed(q),
      ),
    );
    const { type } = setup({ q: "a or b", mode: "native" }, handler);
    await pass(300);
    await type("a OR b");
    await pass(300);
    const line = screen.getByRole("button", { name: /Searched query: 1 warning/ });
    fireEvent.click(line);
    expect(screen.getByText("or is a word")).toBeTruthy();
  });
});

describe("submit", () => {
  it("Enter pushes the reducer's URL (q and mode, page reset); Shift-Enter inserts a newline instead", async () => {
    const { type, view } = setup({ q: "old", mode: "native", sort: "year_desc", page: 3 });
    await type("trust* AND bench");
    fireEvent.change(screen.getByRole("combobox", { name: "Syntax" }), { target: { value: "scholar" } });
    fireEvent.keyDown(view.contentDOM, { key: "Enter", shiftKey: true });
    expect(nav.push).not.toHaveBeenCalled();
    expect(view.state.doc.toString()).toBe("trust* AND bench\n");
    await type("trust* AND bench");
    fireEvent.keyDown(view.contentDOM, { key: "Enter" });
    expect(nav.push).toHaveBeenCalledWith("/search?q=trust*+AND+bench&mode=scholar&sort=year_desc");
  });

  it("the Search button submits even with errors: the server decides", async () => {
    const handler = api((q) =>
      json({ ...parsed(q), errors: [diag("PARSE_UNBALANCED_PAREN", "unclosed", [0, 1])] }),
    );
    const { type } = setup({}, handler);
    await type("(a");
    await pass(300);
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(nav.push).toHaveBeenCalledWith("/search?q=%28a&mode=native");
  });

  it("follows a new URL: the draft becomes the searched query", async () => {
    const { rerender, view } = setup({ q: "one", mode: "native" });
    rerender(<SearchWorkspace state={{ ...INITIAL_STATE, q: "two", mode: "scholar" }} />);
    expect(view.state.doc.toString()).toBe("two");
    expect((screen.getByRole("combobox", { name: "Syntax" }) as HTMLSelectElement).value).toBe("scholar");
  });
});

describe("/parse answers that aren't a parse", () => {
  it("413: the query is far too long to send (ED-11), counted as an error", async () => {
    const handler = api(() =>
      json(
        {
          error: {
            code: "API_BODY_TOO_LARGE",
            message: "The request body is over 65,536 bytes; a query fits in far less.",
          },
        },
        413,
      ),
    );
    const { type, view } = setup({}, handler);
    await type("x".repeat(41_200));
    await pass(300);
    expect(screen.getByText(/far too long to send/).textContent).toBe(
      "✖Error: The query is far too long to send (the server refused a request over 65,536 bytes). A valid " +
        "query is at most 2,000 characters; this one is 41,200. Shorten it.",
    );
    expect(summaryOf(view).textContent).toBe("1 error — not searched yet");
  });

  it("413 whose message gives no byte limit still says the server refused it", async () => {
    const handler = api(() => json({ error: { code: "API_BODY_TOO_LARGE", message: "Too large." } }, 413));
    const { type } = setup({}, handler);
    await type("x".repeat(2_001));
    await pass(300);
    expect(screen.getByText(/far too long to send/).textContent).toBe(
      "✖Error: The query is far too long to send (the server refused it as too large). A valid " +
        "query is at most 2,000 characters; this one is 2,001. Shorten it.",
    );
  });

  it("429: couldn't be checked, the server's message, and Check again asks again", async () => {
    let busy = true;
    const handler = api((q) =>
      busy
        ? json(
            { error: { code: "API_RATE_LIMITED", message: "Too many requests; try again in 3 s." } },
            429,
            { "Retry-After": "3" },
          )
        : json(parsed(q)),
    );
    const { type, view, calls } = setup({}, handler);
    await type("trust");
    await pass(300);
    expect(
      within(screen.getByRole("region", { name: "Diagnostics" })).getByText(/couldn't be checked/)
        .textContent,
    ).toContain("The query couldn't be checked. Too many requests; try again in 3 s.");
    expect(summaryOf(view).textContent).toBe("The query couldn't be checked — not searched yet");
    busy = false;
    fireEvent.click(screen.getByRole("button", { name: "Check again" }));
    await pass(10);
    expect(parseCalls(calls)).toHaveLength(2);
    expect(screen.queryByRole("region", { name: "Diagnostics" })).toBeNull();
  });

  it("503 API_BUSY is shown with its own message", async () => {
    const handler = api(() =>
      json({ error: { code: "API_BUSY", message: "The server is busy." } }, 503, { "Retry-After": "5" }),
    );
    const { type } = setup({}, handler);
    await type("trust");
    await pass(300);
    expect(
      within(screen.getByRole("region", { name: "Diagnostics" })).getByText(/couldn't be checked/)
        .textContent,
    ).toContain("The server is busy.");
  });

  it("a 5xx that isn't JSON is 'busy', never blamed on the query", async () => {
    const handler = api(() => new Response("<html>502 Bad Gateway</html>", { status: 502 }));
    const { type, squiggles } = setup({}, handler);
    await type("trust");
    await pass(300);
    expect(
      within(screen.getByRole("region", { name: "Diagnostics" })).getByText(/couldn't be checked/)
        .textContent,
    ).toContain(
      "The query couldn't be checked: the server is busy or restarting (HTTP 502, not from the search service).",
    );
    expect(squiggles()).toEqual([]);
  });

  it("a 2xx body that isn't JSON is 'busy' with no status", async () => {
    const handler = api(() => new Response("<html>ok</html>", { status: 200 }));
    const { type } = setup({}, handler);
    await type("trust");
    await pass(300);
    expect(
      within(screen.getByRole("region", { name: "Diagnostics" })).getByText(/couldn't be checked/)
        .textContent,
    ).toContain(
      "The query couldn't be checked: the server is busy or restarting (not from the search service).",
    );
  });

  it("a fetch that never answers: the server couldn't be reached", async () => {
    const handler = api(() => Promise.reject(new TypeError("Failed to fetch")));
    const { type } = setup({}, handler);
    await type("trust");
    await pass(300);
    expect(
      within(screen.getByRole("region", { name: "Diagnostics" })).getByText(/couldn't be checked/)
        .textContent,
    ).toContain("The query couldn't be checked: the server couldn't be reached. Check your connection.");
  });
});

describe("a /search refusal (TASK-042 passes it in)", () => {
  it("draws the 422's diagnostics on the submitted q, says it wasn't searched, and explains late expansions", async () => {
    const refusal: SearchRefusal = {
      q: "trust* AND tr*",
      mode: "native",
      error: {
        code: "WILDCARD_TOO_MANY_EXPANSIONS",
        message: "x",
        diagnostics: [
          diag(
            "WILDCARD_TOO_MANY_EXPANSIONS",
            "`tr*` expands to 1,340 terms (more than 200) — use a longer stem.",
            [11, 14],
          ),
        ],
      },
    };
    const { view, squiggles } = setup({ q: refusal.q, mode: "native" }, api(), refusal);
    await pass(300);
    expect(summaryOf(view).textContent).toBe("The query wasn't searched: 1 error");
    expect(squiggles()).toEqual([
      [11, 14, "error", "`tr*` expands to 1,340 terms (more than 200) — use a longer stem."],
    ]);
    expect(
      screen.getByText("Only a search can count expansions, so this appears after Search, not while typing."),
    ).toBeTruthy();
  });

  it("heads the row with an API_ refusal's message and sends Help to the slow-clauses section", async () => {
    const refusal: SearchRefusal = {
      q: '"a b" NEAR/3 c',
      mode: "native",
      error: {
        code: "API_QUERY_TOO_COSTLY",
        message: "This query's position checks would read too many documents.",
        diagnostics: [
          diag(
            "API_QUERY_TOO_COSTLY",
            "This clause's check would read 96,580 documents in abstract.",
            [0, 14],
          ),
        ],
      },
    };
    setup({ q: refusal.q, mode: "native" }, api(), refusal);
    await pass(300);
    expect(screen.getByText("This query's position checks would read too many documents.")).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "Syntax help for API_QUERY_TOO_COSTLY" }).getAttribute("href"),
    ).toBe("/help/syntax#slow-clauses");
  });
});

describe("the empty workspace (W1)", () => {
  it("focuses the editor, loads an example as a draft with its syntax, and never searches", async () => {
    const { view, calls } = setup();
    await pass(10);
    expect(document.activeElement).toBe(view.contentDOM);
    fireEvent.click(screen.getByRole("button", { name: REVIEW_EXAMPLE.q }));
    expect(view.state.doc.toString()).toBe(REVIEW_EXAMPLE.q);
    expect((screen.getByRole("combobox", { name: "Syntax" }) as HTMLSelectElement).value).toBe("scholar");
    expect(nav.push).not.toHaveBeenCalled();
    await pass(300);
    expect(parseCalls(calls).at(-1)?.body).toEqual({ q: REVIEW_EXAMPLE.q, mode: "scholar" });
  });

  it("shows the coverage line from /coverage, and leaves it out when /coverage fails", async () => {
    setup();
    await pass(10);
    expect(screen.getByText(/records indexed/).textContent).toBe(
      "Index c60faee23898 · 39 records indexed · ICLR, ICML, NeurIPS · " +
        "Google Scholar searches run on 2026-09-26 (local time) · Coverage ▸",
    );
    cleanup();
    const failing: Handler = (call) =>
      call.path === "/api/v1/coverage" ? new Response("no", { status: 502 }) : api()(call);
    setup({}, failing);
    await pass(10);
    expect(screen.queryByText(/records indexed/)).toBeNull();
  });
});
