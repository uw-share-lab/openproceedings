import { describe, expect, it } from "vitest";
import { clip } from "./clip";

// Each row's output is what the backend's `diagnostics.clip` gives for the same input (computed with it,
// 2026-10-01), so a refusal here and an API message quote a value alike (TASK-144).
const SAME_AS_BACKEND: readonly (readonly [string, string])[] = [
  ["a`b", "a\\x60b"],
  ["a\nb\t\tc", "a b c"],
  ["\x00\x1b", "\\x00\\x1b"],
  ["x\u202ey", "x\\u202ey"],
  ["a\u2028b", "a b"],
  ["\ufeff", "\\ufeff"],
  ["a\x1cb", "a b"],
  ["a\x85b", "a b"],
  ["\ud800", "\\ud800"],
  ["\u{e0001}", "\\U000e0001"],
  ["k".repeat(50), `${"k".repeat(39)}…`],
  [`${"a".repeat(38)}\``, `${"a".repeat(38)}…`],
  ["😀".repeat(41), `${"😀".repeat(39)}…`],
  ["\\alpha", "\\alpha"],
  [" lead  trail ", " lead trail "],
];

describe("clip (the frontend twin of diagnostics.clip)", () => {
  it.each(SAME_AS_BACKEND)("quotes %j as the backend does", (input, shown) => {
    expect(clip(input)).toBe(shown);
  });

  it("takes a width in code points, never splitting an escape", () => {
    expect(clip("ab`", 5)).toBe("ab…");
    expect(clip("ab`", 6)).toBe("ab\\x60");
    expect(clip("abc", 3)).toBe("abc");
  });
});
