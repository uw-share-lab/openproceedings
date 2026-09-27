import { describe, expect, it } from "vitest";
import {
  countText,
  editorDiagnostics,
  groupRepeats,
  helpHref,
  itemsOf,
  withParentheses,
  type Item,
} from "./diagnostics";

const item = (code: string, span: [number, number] | null, severity: Item["severity"] = "error"): Item => ({
  severity,
  code,
  message: `${code} message`,
  span,
});

describe("itemsOf", () => {
  it("orders errors, then warnings, then translations, each by span, and keeps the server's words", () => {
    const items = itemsOf({
      errors: [
        { code: "B", message: "b", span: [5, 6] },
        { code: "A", message: "a", span: [1, 2] },
      ],
      warnings: [{ code: "W", message: "w", span: null }],
      translations: [{ code: "T", message: "t", span: [0, 1] }],
    });
    expect(items.map((i) => [i.severity, i.code, i.message])).toEqual([
      ["error", "A", "a"],
      ["error", "B", "b"],
      ["warning", "W", "w"],
      ["info", "T", "t"],
    ]);
  });

  it("drops a span that isn't two ordered whole numbers instead of guessing", () => {
    const [bad, backwards] = itemsOf({
      errors: [
        { code: "X", message: "x", span: [1] },
        { code: "Y", message: "y", span: [4, 2] },
      ],
      warnings: [],
      translations: [],
    });
    expect([bad?.span, backwards?.span]).toEqual([null, null]);
  });
});

describe("editorDiagnostics: code points to UTF-16, once", () => {
  it("shifts spans after an astral character (emoji, math letters) by its second unit", () => {
    const text = "😀 𝐱 trust";
    // code points: 😀=0, ' '=1, 𝐱=2, ' '=3, trust=[4,9); UTF-16: 😀=[0,2), 𝐱=[3,5), trust=[6,11)
    expect(
      editorDiagnostics(text, [item("A", [4, 9]), item("B", [2, 3])]).map((d) => [d.from, d.to]),
    ).toEqual([
      [6, 11],
      [3, 5],
    ]);
  });

  it("maps errors, warnings and translations to error, warning and info, message verbatim, code as source", () => {
    const [d] = editorDiagnostics("abc", [item("WARN_CJK_RUN", [0, 3], "warning")]);
    expect(d).toEqual({
      from: 0,
      to: 3,
      severity: "warning",
      message: "WARN_CJK_RUN message",
      source: "WARN_CJK_RUN",
    });
  });

  it("widens a zero-width span by one code point, and clamps to the text", () => {
    const text = "a 𝐱";
    const spans = editorDiagnostics(text, [item("A", [0, 0]), item("B", [3, 3]), item("C", [1, 99])]);
    expect(spans.map((d) => [d.from, d.to])).toEqual([
      [0, 1],
      [2, 4], // at the end: widened backwards over the astral character, both of its units
      [1, 4],
    ]);
  });

  it("draws nothing for a diagnostic without a span", () => {
    expect(editorDiagnostics("abc", [item("A", null)])).toEqual([]);
  });
});

describe("groupRepeats", () => {
  it("makes one group per severity and code, where its first item was", () => {
    const groups = groupRepeats([
      item("A", [0, 1]),
      item("B", [2, 3]),
      item("A", [4, 5]),
      item("A", [6, 7], "warning"),
    ]);
    expect(groups.map((g) => [g.severity, g.code, g.items.length])).toEqual([
      ["error", "A", 2],
      ["error", "B", 1],
      ["warning", "A", 1],
    ]);
  });
});

describe("countText (ED-5)", () => {
  it.each([
    [[], ""],
    [[item("A", null)], "1 error"],
    [[item("A", null), item("B", null), item("W", null, "warning")], "2 errors, 1 warning"],
    [[item("W", null, "warning"), item("W", null, "warning")], "2 warnings"],
    [[item("T", null, "info")], ""],
  ] as [Item[], string][])("%j → %j", (items, text) => {
    expect(countText(items)).toBe(text);
  });
});

describe("helpHref", () => {
  it("links each code to its section, and the two slow-clause codes to one", () => {
    expect(helpHref("PARSE_UNBALANCED_PAREN")).toBe("/help/syntax#parse_unbalanced_paren");
    expect(helpHref("API_TOO_MANY_VERIFIED_CLAUSES")).toBe("/help/syntax#slow-clauses");
    expect(helpHref("API_QUERY_TOO_COSTLY")).toBe("/help/syntax#slow-clauses");
  });
});

describe("withParentheses (Load with parentheses)", () => {
  const mixed = (reading: string, span: [number, number]): Item => ({
    severity: "warning",
    code: "WARN_MIXED_AND_OR",
    message: `AND binds tighter than OR, so this is read as \`${reading}\` — add parentheses if you meant something else.`,
    span,
  });

  it("splices the server's reading over the warning's span", () => {
    expect(withParentheses("x AND (a OR b AND c)", mixed("a OR (b AND c)", [7, 19]))).toBe(
      "x AND (a OR (b AND c))",
    );
  });

  it("splices at UTF-16 positions after an astral character", () => {
    expect(withParentheses("𝐱 a OR b c", mixed("a OR (b c)", [2, 10]))).toBe("𝐱 a OR (b c)");
  });

  it("keeps the Scholar-mode sentence after the reading", () => {
    const item = mixed("a OR (b c)", [0, 8]);
    const scholar = {
      ...item,
      message: `${item.message} Google Scholar binds OR tighter, so it would have grouped this the other way.`,
    };
    expect(withParentheses("a OR b c", scholar)).toBe("a OR (b c)");
  });

  it("offers nothing for a reading the server shortened, another code, or a span that doesn't fit", () => {
    expect(withParentheses("a OR b c", mixed("a OR (b…", [0, 8]))).toBeNull();
    expect(withParentheses("a OR b c", { ...mixed("a", [0, 8]), code: "WARN_CJK_RUN" })).toBeNull();
    expect(withParentheses("a", mixed("a OR (b c)", [0, 8]))).toBeNull();
  });
});
