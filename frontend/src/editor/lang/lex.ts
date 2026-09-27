/**
 * Where each lexeme of a query starts and ends, and its class: the token boundaries of the server's lexer
 * (`backend/src/openproceedings/query/lexer.py`), for **highlighting only** (codemirror-lezer skill).
 *
 * This decides nothing about the query. It reports no error and no warning, never normalises a term and never
 * says whether the query parses: `POST /parse` does all of that. It exists so that a colour always sits on the
 * same characters as the server's lexeme, which `grammar.test.ts` checks against every backend golden input
 * (`lexer-golden.json`, generated from `lexer.py`, so the two cannot drift silently). The character classes are
 * imported from `lexer-tables.json`, generated from the same module.
 *
 * Positions are **code points**, as in `lexer.py` (an astral character is one position). The Lezer tokenizer
 * (`tokens.ts`) reads the document through a `Source` and converts the end back to UTF-16 units.
 */
import tables from "./lexer-tables.json";

/** A lexeme's class. `BAD_NEAR` is a malformed `NEAR/…`, for which the server emits no lexeme (only an error). */
export type LexemeKind =
  | "LPAREN"
  | "RPAREN"
  | "PIPE"
  | "AND"
  | "OR"
  | "NOT"
  | "MINUS"
  | "NEAR"
  | "BAD_NEAR"
  | "FIELD"
  | "UNKNOWN_FIELD"
  | "PHRASE"
  | "RANGE"
  | "WILDCARD"
  | "WORD";

/** The text, one code point per position; `at(k)` is `undefined` past the end and before the start. */
export interface Source {
  at(k: number): string | undefined;
}

const set = (chars: string): ReadonlySet<string> => new Set(Array.from(chars));

const QUOTES = set(tables.quotes);
const CLOSERS: ReadonlyMap<string, ReadonlySet<string>> = new Map(
  Object.entries(tables.closers).map(([open, close]) => [open, set(close)]),
);
const LPARENS = set(tables.lparens);
const RPARENS = set(tables.rparens);
const PIPES = set(tables.pipes);
const COLONS = set(tables.colons);
const MINUSES = set(tables.minuses);
const STARS = set(tables.stars);
const DOLLARS = set(tables.dollars);
const FIELDS: ReadonlySet<string> = new Set(tables.fields);
const ACCENT_SYMBOLS = set(tables.accent_symbols);
const ACCENT_LETTERS = set(tables.accent_letters);
const SPACE = set(tables.space);
const DIGIT_NOT_ND = set(tables.digit_not_nd);
const BREAKS: ReadonlySet<string> = new Set([...LPARENS, ...RPARENS, ...PIPES]);
const OPERATORS: Readonly<Record<string, LexemeKind>> = { AND: "AND", OR: "OR", NOT: "NOT" };

/** Python's `str.isspace()`. */
const isSpace = (c: string | undefined): boolean => c !== undefined && SPACE.has(c);
/** Python's `str.isdigit()`. */
const isDigit = (c: string | undefined): boolean =>
  c !== undefined && (/^\p{Nd}$/u.test(c) || DIGIT_NOT_ND.has(c));
const isAsciiAlpha = (c: string | undefined): boolean => c !== undefined && /^[A-Za-z]$/.test(c);
const isAsciiAlnum = (c: string | undefined): boolean => c !== undefined && /^[A-Za-z0-9]$/.test(c);
const isAscii = (c: string | undefined): boolean => c !== undefined && c.codePointAt(0)! < 0x80;
const has = (s: ReadonlySet<string>, c: string | undefined): boolean => c !== undefined && s.has(c);
/** Python's regex `[^\W\d_]` (a letter, or a number that is not a decimal digit) and `\w`. */
const isFieldStart = (c: string | undefined): boolean => c !== undefined && /^[\p{L}\p{Nl}\p{No}]$/u.test(c);
const isWordChar = (c: string | undefined): boolean => c !== undefined && /^[\p{L}\p{N}_]$/u.test(c);

/** `q[from:to]` as a string. */
function slice(q: Source, from: number, to: number): string {
  let out = "";
  for (let k = from; k < to; k++) out += q.at(k) ?? "";
  return out;
}

/** `lexer._step`: the index after `j`; a backslash also takes the (non-space) character after it. */
function step(q: Source, j: number): number {
  const next = q.at(j + 1);
  return q.at(j) === "\\" && next !== undefined && !isSpace(next) ? j + 2 : j + 1;
}

/** The first index at or after `i` whose character satisfies `pred`, or the end. */
function firstFrom(q: Source, i: number, pred: (c: string) => boolean): number {
  let k = i;
  for (let c = q.at(k); c !== undefined && !pred(c); c = q.at(++k));
  return k;
}

/** `normalize._find` over `text[..limit)`: the next unescaped `closer` at or after `start`, or -1. */
function findCloser(text: Source, start: number, limit: number, closer: string): number {
  const cs = Array.from(closer);
  for (let j = start; j < limit; j += text.at(j) === "\\" ? 2 : 1) {
    if (j + cs.length <= limit && cs.every((c, k) => text.at(j + k) === c)) return j;
  }
  return -1;
}

/** `normalize._find_closing_dollar` over `text[..limit)` (Pandoc's rule for `$…$`). */
function closingDollar(text: Source, i: number, limit: number): number {
  if (i + 1 >= limit || isSpace(text.at(i + 1))) return -1;
  let j = i + 1;
  while (j < limit) {
    const c = text.at(j);
    if (c === "\\") {
      j += 2;
      continue;
    }
    if (c === "$") {
      const next = j + 1 < limit ? text.at(j + 1) : undefined;
      if (next === "$") return -1;
      if (!isSpace(text.at(j - 1)) && !isDigit(next)) return j;
    }
    j += 1;
  }
  return -1;
}

/** `normalize._script_join` over `text[..limit)`. */
function scriptJoin(text: Source, i: number, limit: number): number {
  if (i + 1 >= limit) return -1;
  const next = text.at(i + 1);
  if (isAsciiAlnum(next)) return i;
  if (next !== "{") return -1;
  let k = i + 2;
  while (k < limit && isAsciiAlnum(text.at(k))) k++;
  return k > i + 2 && k < limit && text.at(k) === "}" ? k : -1;
}

/**
 * `normalize.math_regions(q[from:to])`, as absolute `[start, end)` pairs: the LaTeX math regions (`$…$`,
 * `$$…$$`, `\(…\)`, `\[…\]`) exactly as the tokenizer's scan finds them. Only the steps that move the scan
 * position are mirrored; how each character is classified doesn't change where a region starts or ends.
 */
export function mathRegions(q: Source, from: number, to: number): [number, number][] {
  const regions: [number, number][] = [];
  let mathUntil = -1;
  let closeLen = 0;
  let opened = -1;
  let i = from;
  while (i < to) {
    if (i === mathUntil) {
      i += closeLen;
      regions.push([opened, i]);
      mathUntil = -1;
      closeLen = 0;
      continue;
    }
    const inMath = i < mathUntil;
    const c = q.at(i);
    if (c === "\\" && i + 1 < to) {
      const next = q.at(i + 1);
      if (!inMath && (next === "(" || next === "[")) {
        const close = findCloser(q, i + 2, to, next === "(" ? "\\)" : "\\]");
        if (close >= 0) {
          mathUntil = close;
          closeLen = 2;
          opened = i;
          i += 2;
          continue;
        }
      }
      if (next === "-") {
        i += 2;
        continue;
      }
      if (has(ACCENT_SYMBOLS, next) || (has(ACCENT_LETTERS, next) && i + 2 < to && q.at(i + 2) === "{")) {
        const k = i + 2;
        const dotless = slice(q, k + 1, k + 3);
        if (
          k + 3 < to &&
          q.at(k) === "{" &&
          (dotless === "\\i" || dotless === "\\j") &&
          q.at(k + 3) === "}"
        ) {
          i = k + 4;
        } else if (k + 2 < to && q.at(k) === "{" && q.at(k + 2) === "}") {
          i = k + 3;
        } else {
          i = k;
        }
        continue;
      }
      if (isAsciiAlpha(next)) {
        let j = i + 1;
        while (j < to && isAsciiAlpha(q.at(j))) j++;
        i = j; // `\not\in`, `\in` + U+0338: what else the tokenizer takes here is never a `$` or a `\`
        continue;
      }
      i += isAscii(next) ? 2 : 1;
      continue;
    }
    if (c === "\\") {
      // a backslash at the very end: nothing follows it
    } else if (inMath && (c === "^" || c === "_")) {
      const close = scriptJoin(q, i, to);
      if (close > i) {
        i += 2;
        continue;
      }
    } else if (c === "$") {
      if (!inMath && i + 1 < to && q.at(i + 1) === "$") {
        const close = findCloser(q, i + 2, to, "$$");
        if (close >= 0) {
          mathUntil = close;
          closeLen = 2;
          opened = i;
        }
        i += 2;
        continue;
      }
      if (!inMath) {
        const close = closingDollar(q, i, to);
        if (close >= 0) {
          mathUntil = close;
          closeLen = 1;
          opened = i;
        }
      }
    }
    i += 1;
  }
  return regions;
}

/** `_Lexer.math_run`: the end of LaTeX math opening at `i` and closing at a word boundary before `limit`, or -1. */
function mathRun(q: Source, i: number, limit: number): number {
  if (q.at(i) !== "$") return -1;
  let end: number;
  if (i + 1 < limit && q.at(i + 1) === "$") {
    const close = findCloser(q, i + 2, limit, "$$");
    if (close < 0) return -1;
    end = close + 2;
  } else {
    if (i + 1 >= limit || isSpace(q.at(i + 1))) return -1;
    // the first unescaped `$` after `i` that ends an inline-math scan (`dollar_stops`)
    end = -1;
    let backslashes = 0;
    for (let k = i + 1; k < limit; k++) {
      const c = q.at(k);
      if (c === "$" && backslashes % 2 === 0) {
        const next = q.at(k + 1);
        if (next === "$") return -1; // `$$` inside inline math stops it without closing
        if (!isSpace(q.at(k - 1)) && !isDigit(next)) {
          end = k + 1;
          break;
        }
      }
      backslashes = c === "\\" ? backslashes + 1 : 0;
    }
    if (end < 0) return -1;
  }
  const after = q.at(end);
  return end === limit || isSpace(after) || has(BREAKS, after) || has(QUOTES, after) ? end : -1;
}

/** `_Lexer.word_end`: the end of the word at `i`. */
function wordEnd(q: Source, i: number): number {
  const stop = firstFrom(q, i, (c) => isSpace(c) || QUOTES.has(c) || BREAKS.has(c));
  const mathish = firstFrom(q, i, (c) => c === "$" || c === "\\");
  if (mathish >= stop) return stop;
  const limit = firstFrom(q, i, (c) => QUOTES.has(c));
  const math = mathRun(q, i, limit);
  if (math > 0) return math;
  // the whitespace- and quote-delimited chunk holding `i`, and its math regions
  let chunkEnd = i;
  for (let c = q.at(chunkEnd); c !== undefined && !isSpace(c) && !QUOTES.has(c); c = q.at(chunkEnd)) {
    chunkEnd = step(q, chunkEnd);
  }
  const mathEnds = new Map(mathRegions(q, i, chunkEnd));
  let j = i;
  while (j < chunkEnd) {
    const end = mathEnds.get(j);
    if (end !== undefined) j = end;
    else if (has(BREAKS, q.at(j))) break;
    else j = step(q, j);
  }
  return Math.min(j, chunkEnd);
}

/** `_Lexer.word`'s wildcard test: a `*` or `$` (outside math, not currency) as the word's last character. */
function isWildcard(q: Source, start: number, end: number): boolean {
  const regions = mathRegions(q, start, end);
  let last = -1;
  let k = start;
  while (k < end) {
    const c = q.at(k);
    if (c === "\\") {
      k += 2;
      continue;
    }
    const inMath = regions.some(([a, b]) => a <= k && k < b);
    const currency = has(DOLLARS, c) && k + 1 < end && isDigit(q.at(k + 1));
    if ((has(STARS, c) || has(DOLLARS, c)) && !inMath && !currency) last = k;
    k += 1;
  }
  return last >= 0 && last === end - 1;
}

/** `lexer._small_int`: the number if it has at most `maxLen` significant digits. */
function smallInt(digits: string, maxLen: number): number | null {
  const significant = digits.replace(/^0+/, "") || "0";
  return significant.length <= maxLen ? Number(significant) : null;
}

function wordOrOperator(q: Source, i: number): { kind: LexemeKind; end: number } {
  const end = wordEnd(q, i);
  const key = slice(q, i, end).normalize("NFKC"); // `ＯＲ` is `OR`, as the tokenizer would read it
  const operator = OPERATORS[key];
  if (operator !== undefined) return { kind: operator, end };
  const near = /^NEAR\/([0-9]+)$/.exec(key);
  if (near !== null) {
    const n = smallInt(near[1] ?? "", 3);
    if (n !== null && n <= tables.max_near) return { kind: "NEAR", end };
  }
  if (key.startsWith("NEAR/")) return { kind: "BAD_NEAR", end };
  if (/^[0-9]+\.\.[0-9]+$/.test(key)) return { kind: "RANGE", end };
  return { kind: isWildcard(q, i, end) ? "WILDCARD" : "WORD", end };
}

/** `_Lexer.negates`: the `-` at `i` is NOT when it starts a primary and something follows it directly. */
function negates(q: Source, i: number): boolean {
  const prev = q.at(i - 1) ?? " ";
  const next = q.at(i + 1) ?? " ";
  const starts = isSpace(prev) || LPARENS.has(prev) || PIPES.has(prev) || COLONS.has(prev);
  return starts && !isSpace(next) && !RPARENS.has(next) && !PIPES.has(next) && !MINUSES.has(next);
}

/** `lexer._FIELD` at `i`: a letter, then letters/digits/`_`, then a colon. Returns the end, or -1. */
function fieldEnd(q: Source, i: number): number {
  if (!isFieldStart(q.at(i))) return -1;
  let k = i + 1;
  while (isWordChar(q.at(k))) k++;
  return has(COLONS, q.at(k)) ? k + 1 : -1;
}

/** `_Lexer.phrase`: a phrase runs to the next unescaped quote of its opener's family, or to the end. */
function phraseEnd(q: Source, i: number): number {
  const closers = CLOSERS.get(q.at(i) ?? "") ?? QUOTES;
  let j = i + 1;
  for (let c = q.at(j); c !== undefined && !closers.has(c); c = q.at(j)) j = step(q, j);
  return q.at(j) === undefined ? j : j + 1;
}

/**
 * The lexeme starting at `i`, which must be a non-space character: its class and its end (code points).
 * The rules are tried in `_Lexer.run`'s order: a parenthesis or `|`, a quote, a negating `-`, a field, a word.
 */
export function lexemeAt(q: Source, i: number): { kind: LexemeKind; end: number } {
  const c = q.at(i) ?? "";
  if (LPARENS.has(c)) return { kind: "LPAREN", end: i + 1 };
  if (RPARENS.has(c)) return { kind: "RPAREN", end: i + 1 };
  if (PIPES.has(c)) return { kind: "PIPE", end: i + 1 };
  if (QUOTES.has(c)) return { kind: "PHRASE", end: phraseEnd(q, i) };
  if (MINUSES.has(c) && negates(q, i)) return { kind: "MINUS", end: i + 1 };
  const field = fieldEnd(q, i);
  if (field >= 0) {
    // `.toLowerCase()` of the name, as `lexer.py` lowercases it (every known field name is ASCII)
    const name = slice(q, i, field - 1).toLowerCase();
    return { kind: FIELDS.has(name) ? "FIELD" : "UNKNOWN_FIELD", end: field };
  }
  return wordOrOperator(q, i);
}

export { isSpace };

/** A string as a `Source` (code points). */
export function stringSource(text: string): Source & { readonly length: number } {
  const cps = Array.from(text);
  return { at: (k) => (k >= 0 ? cps[k] : undefined), length: cps.length };
}

/** Every lexeme of `text`, as `[kind, start, end]` in code points (the shape of `lexer-golden.json`). */
export function lexemes(text: string): [LexemeKind, number, number][] {
  const q = stringSource(text);
  const out: [LexemeKind, number, number][] = [];
  let i = 0;
  while (i < q.length) {
    if (isSpace(q.at(i))) {
      i += 1;
      continue;
    }
    const { kind, end } = lexemeAt(q, i);
    out.push([kind, i, end]);
    i = end;
  }
  return out;
}
