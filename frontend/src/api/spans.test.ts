import { describe, expect, it } from "vitest";
import { codePointLength, codePointSpanToUtf16 } from "./spans";

describe("codePointSpanToUtf16", () => {
  it("is the identity on BMP-only text", () => {
    expect(codePointSpanToUtf16("trust in AI", [6, 8])).toEqual([6, 8]);
    expect(codePointSpanToUtf16("abc", [0, 3])).toEqual([0, 3]);
  });

  it("shifts every later span past an astral character", () => {
    const text = "𝒜 is trust"; // 𝒜 = U+1D49C, two UTF-16 units
    expect(codePointSpanToUtf16(text, [0, 1])).toEqual([0, 2]);
    expect(codePointSpanToUtf16(text, [5, 10])).toEqual([6, 11]);
    const [s, e] = codePointSpanToUtf16(text, [5, 10]);
    expect(text.slice(s, e)).toBe("trust");
  });

  it("handles zero-width spans, including at the ends", () => {
    expect(codePointSpanToUtf16("", [0, 0])).toEqual([0, 0]);
    expect(codePointSpanToUtf16("😀a", [0, 0])).toEqual([0, 0]);
    expect(codePointSpanToUtf16("😀a", [1, 1])).toEqual([2, 2]);
    expect(codePointSpanToUtf16("😀a", [2, 2])).toEqual([3, 3]);
  });

  it.each([[[-1, 2]], [[3, 2]], [[0, 4]], [[0.5, 1]]] as const)(
    "rejects %j on a three-code-point string",
    (span) => {
      expect(() => codePointSpanToUtf16("abc", span)).toThrow(RangeError);
    },
  );
});

describe("codePointLength", () => {
  it("counts code points", () => {
    expect(codePointLength("𝒜b😀")).toBe(3);
    expect("𝒜b😀".length).toBe(5);
  });
});
