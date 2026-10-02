/**
 * Text the client did not write, as a message quotes it between backticks: the frontend twin of the
 * backend's `diagnostics.clip` (error-diagnostics skill, TASK-141, TASK-144), with the same escapes, so a
 * refusal here and an API message read alike. `Coded` pairs backticks, so a backtick in a quoted value
 * would shift every later code span; a newline or a bidi override would reach the page as is.
 */

/**
 * Exactly Python's `str.isspace()` characters, which the backend collapses (not JS `\s`: it adds U+FEFF and
 * leaves out U+001C–U+001F and U+0085).
 */
const WHITESPACE = /[\t\n\v\f\r\x1c-\x1f \x85\xa0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+/gu;
/** Control, format (bidi overrides, zero-width) and lone surrogates: invisible, so written as escapes. */
const INVISIBLE = /^[\p{Cc}\p{Cf}\p{Cs}]$/u;

/** One code point as a message shows it: a backtick or an invisible character as its Python escape. */
function shown(c: string): string {
  if (c !== "`" && !INVISIBLE.test(c)) return c;
  const n = c.codePointAt(0) ?? 0;
  const hex = (width: number) => n.toString(16).padStart(width, "0");
  return n < 0x100 ? `\\x${hex(2)}` : n < 0x10000 ? `\\u${hex(4)}` : `\\U${hex(8)}`;
}

/**
 * `text` as one line of visible characters (whitespace runs are one space; a backtick or an invisible
 * character is escaped), shortened to at most `width` code points with `…`, never splitting an escape.
 */
export function clip(text: string, width = 40): string {
  const pieces: string[] = [];
  let used = 0; // in code points: an escape is ASCII, an astral character one code point but two UTF-16 units
  const size = (piece: string) => [...piece].length;
  for (const c of text.replace(WHITESPACE, " ")) {
    const piece = shown(c);
    if (used + size(piece) > width) {
      while (pieces.length > 0 && used + 1 > width) used -= size(pieces.pop() ?? "");
      return `${pieces.join("")}…`;
    }
    pieces.push(piece);
    used += size(piece);
  }
  return pieces.join("");
}
