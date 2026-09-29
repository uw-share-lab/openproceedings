import { describe, expect, it } from "vitest";
import { EXCERPT_CHARS, excerpt, utf16Spans } from "./excerpt";

describe("utf16Spans (the API's code-point spans, converted once)", () => {
  it("converts after an astral character, sorts and joins touching spans", () => {
    const text = "𝔘 trust and trustworthy";
    // code points: 𝔘=0, space=1, trust=2..7, ' and '=7..12, trustworthy=12..23
    expect(
      utf16Spans(text, [
        [12, 23],
        [2, 7],
        [7, 12],
      ]),
    ).toEqual([[3, 24]]);
    expect(text.slice(3, 8)).toBe("trust");
  });

  it("returns null for a span that doesn't fit the text, rather than guess", () => {
    expect(utf16Spans("abc", [[0, 9]])).toBeNull();
    expect(utf16Spans("abc", [[2, 1]])).toBeNull();
    expect(utf16Spans("abc", [[0]])).toBeNull();
  });

  it("drops empty spans", () => {
    expect(utf16Spans("abc", [[1, 1]])).toEqual([]);
  });
});

describe("excerpt (design W5 excerpt rule: chosen from the spans, never deciding what matched)", () => {
  it("shows an abstract of up to 600 characters whole", () => {
    const text = "x ".repeat(300).trim();
    expect(text.length).toBeLessThanOrEqual(EXCERPT_CHARS);
    const e = excerpt(text, [[4, 5]]);
    expect(e).toEqual({ start: 0, end: text.length, spans: [[4, 5]], cutBefore: false, cutAfter: false });
  });

  it("windows a long abstract around the first highlight, cut at spaces", () => {
    const words = Array.from({ length: 400 }, (_, i) => `w${i}`);
    const text = words.join(" ");
    const at = text.indexOf("w300");
    const e = excerpt(text, [[at, at + 4]]);
    expect(e.cutBefore).toBe(true);
    expect(e.start).toBeLessThan(at);
    expect(text[e.start - 1]).toBe(" ");
    expect(e.spans[0]).toEqual([at - e.start, at - e.start + 4]);
    expect(text.slice(e.start, e.end).slice(...(e.spans[0] ?? [0, 0]))).toBe("w300");
  });

  it("starts at the beginning when nothing in the abstract is highlighted", () => {
    const text = "a".repeat(2000);
    const e = excerpt(text, []);
    expect(e.start).toBe(0);
    expect(e.cutAfter).toBe(true);
    expect(e.end).toBe(EXCERPT_CHARS);
  });

  it("never cuts a surrogate pair and always keeps the first highlight whole (seeded sweep)", () => {
    let seed = 42;
    const rand = (n: number) => {
      seed = (seed * 1103515245 + 12345) % 2 ** 31;
      return seed % n;
    };
    const pieces = ["a", "b", " ", "𝔘", "é", "\n"];
    for (let run = 0; run < 300; run++) {
      const cps = Array.from({ length: 200 + rand(1500) }, () => pieces[rand(pieces.length)] ?? "a");
      const text = cps.join("");
      const units = text.length;
      const s = rand(units);
      let a = s;
      let b = Math.min(units, s + 1 + rand(30));
      if (a > 0 && text.charCodeAt(a) >= 0xdc00 && text.charCodeAt(a) <= 0xdfff) a -= 1;
      if (b < units && text.charCodeAt(b) >= 0xdc00 && text.charCodeAt(b) <= 0xdfff) b += 1;
      const e = excerpt(text, [[a, b]]);
      expect(e.start).toBeLessThanOrEqual(a);
      expect(e.end).toBeGreaterThanOrEqual(b);
      const lowAt = (i: number) => text.charCodeAt(i) >= 0xdc00 && text.charCodeAt(i) <= 0xdfff;
      if (e.start > 0) expect(lowAt(e.start)).toBe(false);
      if (e.end < units) expect(lowAt(e.end)).toBe(false);
      expect(e.spans).toEqual([[a - e.start, b - e.start]]);
    }
  });
});
