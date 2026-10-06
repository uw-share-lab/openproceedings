import { describe, expect, it } from "vitest";
import { byReason, byTerm, withWordForms, type WordForm } from "./word-forms";
import golden from "./word-forms-golden.json";

describe("withWordForms writes the query the server read back (word-forms-golden.json)", () => {
  const offered = golden.cases.filter((c) => c.word_forms !== null);

  it("covers astral characters, a spaced insert and a query with nothing to add", () => {
    expect(offered.some((c) => c.q.length !== [...c.q].length)).toBe(true);
    expect(offered.some((c) => (c.word_forms ?? []).some((f) => f.insert === "$ "))).toBe(true);
    expect(offered.some((c) => (c.word_forms ?? []).length === 0)).toBe(true);
  });

  it.each(offered.map((c) => [c.name, c] as const))("all of them: %s", (_name, c) => {
    expect(withWordForms(c.q, c.word_forms ?? [])).toBe(c.all);
  });

  it.each(offered.map((c) => [c.name, c] as const))("each alone: %s", (_name, c) => {
    const forms = c.word_forms ?? [];
    expect(forms.map((f) => withWordForms(c.q, [f]))).toEqual(c.each);
  });

  it("takes the forms in any order", () => {
    const c = offered.find((x) => x.name === "astral letters before the terms");
    if (c === undefined) throw new Error("no astral case");
    expect(withWordForms(c.q, (c.word_forms ?? []).reverse())).toBe(c.all);
  });
});

describe("withWordForms", () => {
  it("is null when an offset is outside the text, never a guess", () => {
    expect(withWordForms("trust", [{ term: "trustworthy", at: 11, insert: "$" }])).toBeNull();
    expect(withWordForms("trust", [{ term: "trust", at: -1, insert: "$" }])).toBeNull();
    expect(withWordForms("trust", [{ term: "trust", at: 1.5, insert: "$" }])).toBeNull();
  });

  it("leaves the text alone with no forms, and inserts at the very start and end", () => {
    expect(withWordForms("trust", [])).toBe("trust");
    expect(withWordForms("trust", [{ term: "trust", at: 5, insert: "$" }])).toBe("trust$");
    expect(withWordForms("", [{ term: "", at: 0, insert: "$" }])).toBe("$");
  });
});

describe("byTerm", () => {
  it("groups the places one term is written, in the order terms first appear", () => {
    const forms: WordForm[] = [
      { term: "trust", at: 5, insert: "$" },
      { term: "model", at: 11, insert: "$ " },
      { term: "trust", at: 20, insert: "$" },
    ];
    expect(byTerm(forms)).toEqual([
      { term: "trust", forms: [forms[0], forms[2]] },
      { term: "model", forms: [forms[1]] },
    ]);
    expect(byTerm([])).toEqual([]);
  });
});

describe("byReason", () => {
  it("groups the skipped terms by the server's reason, in the order reasons first appear", () => {
    expect(
      byReason([
        { term: "trust", reason: "too_long" },
        { term: "ai", reason: "too_short" },
        { term: "judge", reason: "too_long" },
      ]),
    ).toEqual([
      { reason: "too_long", terms: ["trust", "judge"] },
      { reason: "too_short", terms: ["ai"] },
    ]);
    expect(byReason([])).toEqual([]);
  });
});
