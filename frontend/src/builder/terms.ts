/**
 * What one term box writes (docs/design/2026-09-27-concept-group-builder.md §States: "Term needs quoting",
 * "Pasted list in one term"; pre-pass M5, S9).
 *
 * A term must reach the query as **exactly one** word, wildcard or phrase, so the server reads it as one leaf
 * wherever the builder puts it. Whether a text is one such lexeme is decided with `lex.ts`, the exact mirror
 * of the server lexer (its golden is generated from `lexer.py`), so this never guesses at the language: text
 * that is one lexeme is written as typed; anything else (several words, an operator, a parenthesis, a field
 * the builder doesn't scope with) is written as one phrase, and the chip says so. What the server then makes
 * of it (a warning, an error) is its own answer, shown under the term.
 */
import { lexemes, type LexemeKind } from "@/editor/lang/lex";
import tables from "@/editor/lang/lexer-tables.json";
import type { AstNode, Scope } from "./model";

const ONE_TERM: ReadonlySet<LexemeKind> = new Set(["WORD", "WILDCARD", "PHRASE"]);
/** Lowercase `and`/`or`/`not` are words, with a "did you mean" warning; quoted, they are just words. */
const OPERATOR_WORDS: ReadonlySet<string> = new Set(["and", "or", "not"]);
const QUOTES: ReadonlySet<string> = new Set(Array.from(tables.quotes));
const cpLength = (s: string) => Array.from(s).length;
const cpSlice = (s: string, from: number, to?: number) => Array.from(s).slice(from, to).join("");

/**
 * Whether `text` is exactly one word, wildcard or phrase lexeme, and stays that lexeme where the writer puts
 * it: after `(` or a space, before `)` or a space. (An unterminated phrase `"a` or a trailing backslash `a\`
 * is one lexeme alone but swallows what follows it.)
 */
export function isOneTerm(text: string): boolean {
  const n = cpLength(text);
  const alone = lexemes(text);
  const [only] = alone;
  if (alone.length !== 1 || only === undefined || !ONE_TERM.has(only[0]) || only[1] !== 0 || only[2] !== n) {
    return false;
  }
  const same = (context: string, at: number) => {
    const found = lexemes(context).find(([, s]) => s === at);
    return found !== undefined && found[0] === only[0] && found[2] === at + n;
  };
  return same(`(${text})`, 1) && same(`x ${text} x`, 2);
}

export type TermInput =
  | { readonly kind: "empty" }
  | { readonly kind: "term"; readonly text: string; readonly scope: Scope | null; readonly phrased: boolean }
  /** No phrase can hold it (nothing but quote marks and backslashes, say). */
  | { readonly kind: "unwritable" };

/**
 * The term a box's `input` writes. `scope` is `null` unless the input carries its own `title:`/`abstract:`
 * prefix, which then becomes the chip's scope (so a pasted `title:LLM` stays scoped).
 */
export function termFromInput(input: string): TermInput {
  const text = input.trim();
  if (text === "") return { kind: "empty" };
  if (isOneTerm(text)) {
    return OPERATOR_WORDS.has(text)
      ? { kind: "term", text: `"${text}"`, scope: null, phrased: false }
      : { kind: "term", text, scope: null, phrased: false };
  }
  const lx = lexemes(text);
  const [field, rest] = lx;
  if (lx.length === 2 && field !== undefined && rest !== undefined && field[0] === "FIELD") {
    const name = cpSlice(text, field[1], field[2] - 1).toLowerCase();
    const body = cpSlice(text, rest[1]);
    if ((name === "title" || name === "abstract") && isOneTerm(body)) {
      const inner = termFromInput(body);
      return inner.kind === "term" ? { ...inner, scope: name } : inner;
    }
  }
  return phraseOf(text);
}

/**
 * `text` as one phrase: quote marks become spaces (inside a phrase they are punctuation the tokenizer drops)
 * and backslashes go (one would escape the closing quote), then the result must lex as one phrase.
 */
export function phraseOf(text: string): TermInput {
  const body = Array.from(text)
    .map((c) => (QUOTES.has(c) ? " " : c === "\\" ? "" : c))
    .join("")
    .replace(/\s+/gu, " ")
    .trim();
  if (body === "") return { kind: "unwritable" };
  const phrase = `"${body}"`;
  return isOneTerm(phrase)
    ? { kind: "term", text: phrase, scope: null, phrased: true }
    : { kind: "unwritable" };
}

/**
 * The items of a pasted list: text holding `,`, `;`, `|`, a line break, or `OR`/`or` between words. `null`
 * when it isn't a list of two or more (an `or`/`OR` separator is dropped, not searched).
 */
export function listItems(input: string): string[] | null {
  if (!/[,;|\n]|\s(?:OR|or)\s/u.test(input)) return null;
  const items = input
    .split(/[,;|\n]|\s+(?:OR|or)\s+/u)
    .map((s) => s.trim())
    .filter((s) => s !== "");
  return items.length >= 2 ? items : null;
}

type Leaf = Extract<AstNode, { kind: "term" | "wildcard" | "phrase" }>;
type Item = Extract<AstNode, { kind: "phrase" }>["items"][number];

const itemText = (i: Item) => (i.kind === "term" ? i.token : `${i.stem}${i.op}`);

/**
 * A leaf of a query as its term text: the source slice as typed when it is one lexeme (with the leaf's own
 * `title:`/`abstract:` prefix taken off, since the scope carries it), else the leaf's normalised tokens in
 * the canonical spelling (a Scholar-mode unquoted phrase `large language model$` becomes
 * `"large language model$"`).
 */
export function leafTermText(slice: string, leaf: Leaf): string {
  const text = slice.trim();
  if (isOneTerm(text)) return text;
  const lx = lexemes(text);
  const [field, rest] = lx;
  if (lx.length === 2 && field?.[0] === "FIELD" && rest !== undefined) {
    const name = cpSlice(text, field[1], field[2] - 1).toLowerCase();
    const body = cpSlice(text, rest[1]);
    if (name === leaf.field && isOneTerm(body)) return body;
  }
  switch (leaf.kind) {
    case "term":
      return OPERATOR_WORDS.has(leaf.token) ? `"${leaf.token}"` : leaf.token;
    case "wildcard":
      return `${leaf.stem}${leaf.op}`;
    case "phrase":
      return `"${leaf.items.map(itemText).join(" ")}"`;
  }
}
