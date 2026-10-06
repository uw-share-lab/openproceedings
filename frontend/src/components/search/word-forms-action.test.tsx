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
  readonly word_forms_skipped?: readonly { term: string; reason: string }[] | null;
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
    word_forms_skipped: [...(c.word_forms_skipped ?? [])] as Parse["word_forms_skipped"],
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
  const notice = () => {
    // the notice's own item: the "Left as typed:" list inside it has items of its own
    const list = screen.getByRole("list", { name: "Translations" });
    const [item] = within(list)
      .getAllByRole("listitem")
      .filter((li) => li.parentElement === list);
    if (item === undefined) throw new Error("no notice");
    return item;
  };
  return { ...r, view, notice };
}

/** The "Left as typed:" list: each named term the server offers no `$` for, grouped by its reason. */
function items(notice: HTMLElement): string[] {
  const list = within(notice).getByRole("list", { name: "Left as typed:" });
  return within(list)
    .getAllByRole("listitem")
    .map((li) => li.textContent ?? "");
}

/** Said under the notice in both its states (copy ED-19): full text, not word forms, is most of the gap. */
const FULL_TEXT =
  "Google Scholar also reads the full text of a paper; openproceedings matches titles and abstracts only. " +
  "Most of a difference in counts can come from that, and $ does not recover it.";

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

    // the notice names `ai`, `c` and `or`, and the server found no place for a `$`: said, with its reasons
    const again = await setup(caseOf("no named term can take a $"));
    expect(screen.queryByRole("button", { name: /^Add \$/ })).toBeNull();
    expect(again.notice().textContent).toContain("$ can't be added to these terms for you.");
    expect(items(again.notice())).toEqual([
      "ai: too few letters or digits for a $.",
      "c: a symbol where the $ would go.",
      "or: a lowercase and, or or not.",
    ]);
    expect(again.notice().textContent).toContain("Type a wildcard yourself where one is valid.");
    expect(again.notice().textContent).not.toContain("benchmark$");
    expect(again.notice().textContent).toContain(FULL_TEXT);
  });

  it("near the length limit, offers the terms that fit and names the rest with the server's reasons", async () => {
    const c = caseOf("near the length cap");
    const { view, notice } = await setup(c);
    expect(c.word_forms_skipped).toContainEqual({ term: "trust", reason: "too_long" });
    expect(items(notice())).toEqual([
      "trust, judge: no room for a $ under the length limit.",
      "ai: too few letters or digits for a $.",
    ]);
    const add = within(notice()).getByRole("button", { name: "Add $ to the 2 terms that fit" });
    const described = document.getElementById(add.getAttribute("aria-describedby") ?? "");
    expect(described?.textContent).toContain("that fits under the length limit");
    fireEvent.click(within(notice()).getByRole("button", { name: "Choose terms" }));
    const labels = within(screen.getByRole("group", { name: "Add $ to" }))
      .getAllByRole("checkbox")
      .map((b) => b.closest("label")?.textContent);
    expect(labels).toEqual(["model", "agent"]); // only the terms that fit can be ticked
    fireEvent.click(add);
    expect(view.state.doc.toString()).toBe(c.all);
    expect(c.all).toMatch(/ OR model\$ OR agent\$ OR judge OR AI$/);
  });

  it("reads a reason it doesn't know as a term left as typed, and lists at most 8 terms of one reason", async () => {
    const terms = ["alpha", "beta", "gamma", "delta", "epsilon", "zeta", "theta", "iota", "kappa", "lambda"];
    const q = `${terms.join(" ")} trust`;
    const report: Report = {
      q,
      mode: "scholar",
      notice: "exact",
      word_forms: [{ term: "trust", at: [...q].length, insert: "$" }],
      word_forms_skipped: [
        ...terms.map((term) => ({ term, reason: "too_long" })),
        { term: "omega", reason: "a_reason_from_a_newer_server" }, // an open enum (spec 04 §Conventions)
      ],
    };
    const { notice } = await setup(report);
    expect(items(notice())).toEqual([
      "alpha, beta, gamma, delta, epsilon, zeta, theta, iota and 2 more: no room for a $ under the length limit.",
      "omega: can't take a $ as typed.",
    ]);
    expect(within(notice()).getByRole("button", { name: "Add $ to the 1 term that fits" })).toBeTruthy();
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

  it("leaves a lowercase and/not out of the offer and says why, with the chooser open or not", async () => {
    const c = caseOf("lowercase operator words are left alone");
    const { view, notice } = await setup(c);
    expect(items(notice())).toEqual(["and, not: a lowercase and, or or not."]);
    fireEvent.click(within(notice()).getByRole("button", { name: "Choose terms" }));
    const group = screen.getByRole("group", { name: "Add $ to" });
    const labels = within(group)
      .getAllByRole("checkbox")
      .map((b) => b.closest("label")?.textContent);
    expect(labels).toEqual(["trust", "llm", "model"]);
    expect(items(notice())).toEqual(["and, not: a lowercase and, or or not."]);
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
