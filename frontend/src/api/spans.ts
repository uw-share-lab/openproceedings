/**
 * The one place API spans become JavaScript string indices (nextjs-conventions §Gotchas, spec 04 §Conventions).
 *
 * The API reports half-open `[start, end)` ranges in Unicode **code points** over the raw source string
 * (the stored title/abstract for highlights, `q` for diagnostics and clause spans). JavaScript strings index
 * UTF-16 code units, so an astral character (math letters, emoji) is one code point but two units. Convert
 * here, exactly once, and nowhere else.
 */
export type CodePointSpan = readonly [start: number, end: number];
export type Utf16Span = readonly [start: number, end: number];

export function codePointSpanToUtf16(text: string, span: CodePointSpan): Utf16Span {
  const [start, end] = span;
  if (!Number.isInteger(start) || !Number.isInteger(end) || start < 0 || end < start) {
    throw new RangeError(`invalid code-point span [${start}, ${end})`);
  }
  let cp = 0;
  let unit = 0;
  let startUnit = start === 0 ? 0 : -1;
  for (const ch of text) {
    unit += ch.length;
    cp += 1;
    if (cp === start) startUnit = unit;
    if (cp === end) return [startUnit, unit];
  }
  if (end === 0) return [0, 0];
  throw new RangeError(`code-point span [${start}, ${end}) is outside a string of ${cp} code points`);
}

/** Length of `text` in code points (the unit every API span uses). */
export function codePointLength(text: string): number {
  return [...text].length;
}
