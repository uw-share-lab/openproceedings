// @vitest-environment jsdom
/**
 * "Add `$`" on the no-stemming notice (TASK-175; spec 05 §Components 1). `/parse` answers with the server's
 * own report for each query (`word-forms-golden.json`, generated from `query/wordforms.py`), so what the
 * action writes is checked against the strings the server read back.
 */
import { undo } from "@codemirror/commands";
import { EditorView } from "@codemirror/view";
import { act, cleanup, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import type { Schemas } from "@/api/client";
import { INITIAL_STATE, type SearchState } from "@/lib/search-state";
import golden from "@/lib/word-forms-golden.json";
import { json, META, parsed, pass, polyfillLayout, renderWithApi, type Handler } from "@/test/api-stub";
import coverageFixture from "@/components/coverage/coverage-fixture.json";
import { SearchWorkspace } from "./search-workspace";

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

type Parse = Schemas["ParseResponse"];
type Case = (typeof golden.cases)[number];

function caseOf(name: string): Case {
  const found = golden.cases.find((c) => c.name === name);
  if (found === undefined) throw new Error(`no golden case ${name}`);
  return found;
}

/** What `/parse` says about one query's word forms: a golden case, or a stand-in a test spells out. */
interface Report {
  readonly q: string;
  readonly mode: string;
  readonly notice: string | null;
  readonly word_forms: readonly { term: string; at: number; insert: string }[] | null;
}

/** The `/parse` answer for `q`: the report's notice and word forms when `q` has one, else a plain parse. */
function answer(reports: readonly Report[], q: string, mode: string): Parse {
  const c = reports.find((x) => x.q === q && x.mode === mode);
  const base = parsed(q, { mode: mode === "scholar" ? "scholar" : "native" });
  if (c === undefined || c.word_forms === null) return base;
  return {
    ...base,
    translations:
      c.notice === null
        ? []
        : [{ code: "COMPAT_NO_STEMMING", message: c.notice, span: [0, [...q].length], reading: null }],
    word_forms: [...c.word_forms],
  };
}

const handlerFor =
  (reports: readonly Report[]): Handler =>
  (call) => {
    if (call.path === "/api/v1/meta") return json(META);
    if (call.path === "/api/v1/coverage") return json(coverageFixture);
    if (call.path === "/api/v1/parse") {
      const body = call.body as { q: string; mode: string };
      return json(answer(reports, body.q, body.mode));
    }
    return json({ error: { code: "API_NOT_FOUND", message: "no" } }, 404);
  };

async function setup(c: Report, state: Partial<SearchState> = {}) {
  const r = renderWithApi(
    <SearchWorkspace state={{ ...INITIAL_STATE, q: c.q, mode: "scholar", ...state }} />,
    handlerFor([c, ...golden.cases]),
  );
  const view = EditorView.findFromDOM(r.container.querySelector(".cm-editor") as HTMLElement);
  if (view === null) throw new Error("no editor");
  await pass(300);
  const notice = () => within(screen.getByRole("list", { name: "Translations" })).getByRole("listitem");
  return { ...r, view, notice };
}

/** Said under the notice in both its states (copy ED-19): full text, not word forms, is most of the gap. */
const FULL_TEXT =
  "Google Scholar also reads the full text of a paper; openproceedings matches titles and abstracts only. " +
  "Most of a difference in counts usually comes from that, and $ does not recover it.";

describe("Add $ on the no-stemming notice", () => {
  it("writes $ after every term the server offered, as a draft: nothing is searched until Search", async () => {
    const c = caseOf("phrase: last word only");
    const { view, notice } = await setup(c);
    // the server's message, its backticked runs drawn as code
    expect(notice().textContent).toContain(c.notice?.replaceAll("`", ""));
    expect(notice().textContent).toContain(FULL_TEXT);
    const all = within(notice()).getByRole("button", { name: "Add $ to all 3 terms" });
    const described = document.getElementById(all.getAttribute("aria-describedby") ?? "");
    expect(described?.textContent).toMatch(/Nothing is searched until you press Search\.$/);

    fireEvent.click(all);
    expect(view.state.doc.toString()).toBe(c.all);
    expect(c.all).toBe('("large language model$" OR LLM$) trust$'); // the phrase's last word only
    expect(nav.push).not.toHaveBeenCalled();
    expect(document.activeElement).toBe(view.contentDOM);
    await pass(300);
    expect(screen.getByRole("status").textContent).toBe("not searched yet"); // the summary: a draft

    // Search puts the edited text, `$` and all, in the URL: the query string is the whole result-set state
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(nav.push).toHaveBeenCalledTimes(1);
    const url = new URL(String(nav.push.mock.calls[0]?.[0]), "http://x");
    expect(url.searchParams.get("q")).toBe(c.all);
    expect(url.searchParams.get("mode")).toBe("scholar");
  });

  it("is one undoable edit in the editor, and Revert edits puts the searched query back", async () => {
    const c = caseOf("words");
    const { view } = await setup(c);
    fireEvent.click(screen.getByRole("button", { name: "Add $ to all 2 terms" }));
    expect(view.state.doc.toString()).toBe("LLM$ benchmark$");
    act(() => {
      undo(view);
    });
    expect(view.state.doc.toString()).toBe(c.q);

    await pass(300);
    fireEvent.click(screen.getByRole("button", { name: "Add $ to all 2 terms" }));
    expect(view.state.doc.toString()).toBe("LLM$ benchmark$");
    fireEvent.click(screen.getByRole("button", { name: "Revert edits" }));
    expect(view.state.doc.toString()).toBe(c.q);
  });

  it("says in words that $ is one more character, not every ending Google Scholar counts", async () => {
    const { notice } = await setup(caseOf("words"));
    expect(notice().textContent).toContain(
      "$ after a term also matches it with one more letter or digit: benchmark$ matches benchmark and " +
        "benchmarks, not benchmarking. That is fewer forms than Google Scholar counts; type * for any ending.",
    );
  });

  it("Choose terms adds $ only to the ticked terms, in every place each is written", async () => {
    const c = caseOf("each place a term is written");
    const { view, notice } = await setup(c);
    const choose = within(notice()).getByRole("button", { name: "Choose terms" });
    expect(choose.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByRole("group", { name: "Add $ to" })).toBeNull();
    fireEvent.click(choose);
    expect(choose.getAttribute("aria-expanded")).toBe("true");
    const group = screen.getByRole("group", { name: "Add $ to" });
    expect(choose.getAttribute("aria-controls")).toBe(group.id);
    const boxes = within(group).getAllByRole("checkbox");
    expect(boxes.map((b) => b.closest("label")?.textContent)).toEqual(["trust (written 2 times)", "model"]);

    // nothing ticked: the button stays focusable, says why, and does nothing
    const add = within(group).getByRole("button", { name: "Add $ to the ticked terms" });
    expect(add.getAttribute("aria-disabled")).toBe("true");
    const why = document.getElementById(add.getAttribute("aria-describedby") ?? "");
    expect(why?.textContent).toBe("Tick at least one term first.");
    expect(why?.className).not.toContain("sr-only"); // shown, not only read to a screen reader
    fireEvent.click(add);
    expect(view.state.doc.toString()).toBe(c.q);

    fireEvent.click(within(group).getByRole("checkbox", { name: /^trust/ }));
    expect(add.getAttribute("aria-disabled")).toBeNull();
    fireEvent.click(add);
    expect(view.state.doc.toString()).toBe("trust$ OR (trust$ AND model)");
    expect(nav.push).not.toHaveBeenCalled();
  });

  it("marks a phrase, whose $ goes on its last word", async () => {
    const { notice } = await setup(caseOf("phrase: last word only"));
    fireEvent.click(within(notice()).getByRole("button", { name: "Choose terms" }));
    const labels = within(screen.getByRole("group", { name: "Add $ to" }))
      .getAllByRole("checkbox")
      .map((b) => b.closest("label")?.textContent);
    expect(labels).toEqual(["large language model (phrase: on its last word)", "llm", "trust"]);
  });

  it("writes the space the server asked for between two words of one unspaced run, after astral letters", async () => {
    const c = caseOf("astral letters before the terms");
    const { view } = await setup(c);
    fireEvent.click(screen.getByRole("button", { name: /^Add \$ to all/ }));
    expect(view.state.doc.toString()).toBe(c.all);
    expect(c.all).toContain("(model$ |LLM$)");
  });

  it("offers one term without a chooser", async () => {
    const one: Report = {
      q: "trust",
      mode: "scholar",
      notice: "exact",
      word_forms: [{ term: "trust", at: 5, insert: "$" }],
    };
    const { view, notice } = await setup(one);
    expect(within(notice()).queryByRole("button", { name: "Choose terms" })).toBeNull();
    fireEvent.click(within(notice()).getByRole("button", { name: "Add $ to 1 term" }));
    expect(view.state.doc.toString()).toBe("trust$");
  });

  it("adds only where the server reported a place, and offers nothing when it reported none", async () => {
    const c = caseOf("short stems and symbols are left alone");
    const { notice, view } = await setup(c);
    // the server offered only the phrase "generative AI": `AI`, `C++` and `US$5` are left as typed
    fireEvent.click(within(notice()).getByRole("button", { name: "Add $ to 1 term" }));
    expect(view.state.doc.toString()).toBe('AI C++ US$5 "generative AI$"');
    cleanup();

    // the notice names `ai`, `c` and `or`, and the server found no place for a `$`: said, with the reasons
    const again = await setup(caseOf("no named term can take a $"));
    expect(screen.queryByRole("button", { name: /^Add \$/ })).toBeNull();
    expect(again.notice().textContent).toContain(
      "$ can't be added to these terms for you. A term is left as typed when it has too few letters or " +
        "digits, has a symbol or another $ beside it, or is a lowercase and, or or not. The same happens " +
        "when the query would be over the length limit with $ added. Type a wildcard yourself where one is valid.",
    );
    expect(again.notice().textContent).not.toContain("benchmark$");
    expect(again.notice().textContent).toContain(FULL_TEXT);
  });

  it("says nothing more when the editor holds other text than the notice's", async () => {
    const { view } = await setup(caseOf("no named term can take a $"));
    expect(screen.getByText(/can't be added to these terms for you/)).toBeTruthy();
    act(() => {
      view.dispatch({ changes: { from: 0, insert: "x " } });
    });
    expect(screen.queryByText(/can't be added to these terms for you/)).toBeNull();
  });

  it("ticking only the first word of an unspaced run writes its $ and the space, and leaves the second", async () => {
    const c = caseOf("two words in one unspaced run");
    const { view } = await setup(c);
    fireEvent.click(screen.getByRole("button", { name: "Choose terms" }));
    const group = screen.getByRole("group", { name: "Add $ to" });
    fireEvent.click(within(group).getByRole("checkbox", { name: /^model/ }));
    fireEvent.click(within(group).getByRole("button", { name: "Add $ to the ticked terms" }));
    expect(view.state.doc.toString()).toBe("(model$ |LLM) trust");
    expect(c.each).toContain("(model$ |LLM) trust"); // a string the server's own apply writes
  });

  it("leaves a lowercase and/not out of the offer and says why in the chooser", async () => {
    const c = caseOf("lowercase operator words are left alone");
    const { view, notice } = await setup(c);
    fireEvent.click(within(notice()).getByRole("button", { name: "Choose terms" }));
    const group = screen.getByRole("group", { name: "Add $ to" });
    const labels = within(group)
      .getAllByRole("checkbox")
      .map((b) => b.closest("label")?.textContent);
    expect(labels).toEqual(["trust", "llm", "model"]);
    expect(group.textContent).toContain(
      "A term the notice names that is not listed here can't take $ as typed. A term is left as typed when " +
        "it has too few letters or digits, has a symbol or another $ beside it, or is a lowercase and, or or not.",
    );
    fireEvent.click(screen.getByRole("button", { name: "Add $ to all 3 terms" }));
    expect(view.state.doc.toString()).toBe("trust$ | LLM$ and model$ not");
  });

  it("is withdrawn while the editor holds text the forms were not reported for", async () => {
    const c = caseOf("words");
    const { view } = await setup(c);
    expect(screen.getByRole("button", { name: "Add $ to all 2 terms" })).toBeTruthy();
    act(() => {
      view.dispatch({ changes: { from: 0, insert: "x " } });
    });
    // the notice is still the old text's until /parse answers: its offsets would land in the wrong place
    expect(screen.queryByRole("button", { name: /^Add \$/ })).toBeNull();
  });
});
