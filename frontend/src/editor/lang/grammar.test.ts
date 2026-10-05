import { ensureSyntaxTree, syntaxTree } from "@codemirror/language";
import { EditorState } from "@codemirror/state";
import { query } from "./index";
import goldenV2 from "./lexer-v2-golden.json";
import { TreeFragment, type Tree } from "@lezer/common";
import { buildParserFile } from "@lezer/generator";
import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it, vi } from "vitest";
import { codePointSpanToUtf16 } from "@/api/spans";
import golden from "./lexer-golden.json";
import type { LexemeKind } from "./lex";
import { parser } from "./parser";

const here = import.meta.dirname;

const KIND: Readonly<Record<string, LexemeKind>> = {
  LParen: "LPAREN",
  RParen: "RPAREN",
  Pipe: "PIPE",
  And: "AND",
  Or: "OR",
  Not: "NOT",
  Minus: "MINUS",
  Near: "NEAR",
  BadNear: "BAD_NEAR",
  Field: "FIELD",
  UnknownField: "UNKNOWN_FIELD",
  Phrase: "PHRASE",
  Range: "RANGE",
  Wildcard: "WILDCARD",
  Word: "WORD",
};

/** The tree's tokens as `[kind, from, to]` in UTF-16 units; an error node or an unknown name fails the test. */
function tokens(tree: Tree): [string, number, number][] {
  const out: [string, number, number][] = [];
  tree.iterate({
    enter: (node) => {
      if (node.name === "Query") return;
      out.push([KIND[node.name] ?? `unexpected ${node.name}`, node.from, node.to]);
    },
  });
  return out;
}

/** The golden's code-point spans as UTF-16 units, through the one converter (spans.ts). */
function expected(q: string, lexemes: readonly (string | number)[][]): [string, number, number][] {
  return lexemes.map(([kind, start, end]) => {
    const [from, to] = codePointSpanToUtf16(q, [Number(start), Number(end)]);
    return [String(kind), from, to];
  });
}

describe("parser.ts is generated from query.grammar", () => {
  it("is current (regenerate: npm run gen:grammar --workspace frontend)", () => {
    const grammar = readFileSync(path.join(here, "query.grammar"), "utf8");
    const built = buildParserFile(grammar, { fileName: "src/editor/lang/query.grammar", typeScript: true });
    expect(readFileSync(path.join(here, "parser.ts"), "utf8")).toBe(built.parser);
    expect(readFileSync(path.join(here, "parser.terms.ts"), "utf8")).toBe(built.terms);
  });
});

// The fixture parity the codemirror-lezer skill asks for: every backend golden input, every Trust-Evals
// string and the probes (read from lexer-golden.json, which the backend generates from its own fixtures, so the
// two sides cannot drift) tokenizes to the server lexer's classes at the server's spans, with no error node.
describe("the Lezer tree has the server lexer's tokens", () => {
  it.each(golden.cases.map((c) => [JSON.stringify(c.q).slice(0, 80), c] as const))("%s", (_name, c) => {
    expect(tokens(parser.parse(c.q))).toEqual(expected(c.q, c.tokens));
  });
});

describe("operators are uppercase only (spec 02)", () => {
  it.each([
    ["a OR b", ["WORD", "OR", "WORD"]],
    ["a or b", ["WORD", "WORD", "WORD"]],
    ["a AND b", ["WORD", "AND", "WORD"]],
    ["a and b", ["WORD", "WORD", "WORD"]],
    ["NOT a", ["NOT", "WORD"]],
    ["not a", ["WORD", "WORD"]],
    ["a NEAR/3 b", ["WORD", "NEAR", "WORD"]],
    ["a near/3 b", ["WORD", "WORD", "WORD"]],
  ])("%s", (q, kinds) => {
    expect(tokens(parser.parse(q)).map(([k]) => k)).toEqual(kinds);
  });
});

describe("an astral character counts once in code points and twice in UTF-16", () => {
  it("puts the token after it at the right UTF-16 offset", () => {
    expect(tokens(parser.parse("𝐱 trust*"))).toEqual([
      ["WORD", 0, 2],
      ["WILDCARD", 3, 9],
    ]);
  });
});

// Lezer reuses unchanged parts of the old tree after an edit. A lexeme depends on the character before it
// (`-` negates only after a space or `(`), so an incremental parse must still give the fresh parse's tokens.
describe("incremental reparsing after an edit gives the same tokens as a fresh parse", () => {
  const edits: [string, number, number, string][] = [
    ["trust -bias", 5, 6, ""], // `trust-bias`: one word now
    ["trust-bias", 5, 5, " "], // `trust -bias`: NOT now
    ["a (b) c", 2, 3, ""], // `a b) c`
    ['a "b c" d', 2, 3, ""], // the phrase's opening quote removed
    ["a $x y$ b", 2, 3, ""], // math opener removed
    ["title:x OR y", 5, 6, ""], // `titlex`: no longer a field
    ["𝐱 -a 𝐲", 2, 3, ""], // after an astral character
  ];
  it.each(edits)("%s, replace [%i, %i) with %j", (before, from, to, insert) => {
    const after = before.slice(0, from) + insert + before.slice(to);
    const old = parser.parse(before);
    const fragments = TreeFragment.applyChanges(TreeFragment.addTree(old), [
      { fromA: from, toA: to, fromB: from, toB: from + insert.length },
    ]);
    expect(tokens(parser.parse(after, fragments))).toEqual(tokens(parser.parse(after)));
  });
});

describe("the tokenizer 2 Lezer language has the server's token spans", () => {
  it.each(goldenV2.cases.map((c) => [JSON.stringify(c.q).slice(0, 80), c] as const))("%s", (_name, c) => {
    const state = EditorState.create({ doc: c.q, extensions: [query("2")] });
    // The whole tree, however long it takes: `syntaxTree(state)` is only what CodeMirror parsed within its
    // start-up time budget (wall clock), so on a loaded machine it can be the tree of a prefix of the query.
    const tree = ensureSyntaxTree(state, c.q.length, 60_000);
    expect(tree).not.toBeNull();
    expect(tokens(tree as Tree)).toEqual(expected(c.q, c.tokens));
  });

  it("is judged on the whole tree even when the clock outruns CodeMirror's parse budget", () => {
    // every read of the clock is 30 ms later: the start-up budget is spent at once, as under heavy load
    let now = 0;
    const clock = vi.spyOn(Date, "now").mockImplementation(() => (now += 30));
    try {
      let cut = 0;
      for (const c of goldenV2.cases) {
        const state = EditorState.create({ doc: c.q, extensions: [query("2")] });
        if (syntaxTree(state).length < c.q.length) cut += 1;
        const tree = ensureSyntaxTree(state, c.q.length, Number.MAX_SAFE_INTEGER);
        expect(tree?.length).toBe(c.q.length);
        expect(tokens(tree as Tree)).toEqual(expected(c.q, c.tokens));
      }
      expect(cut).toBeGreaterThan(0); // the budgeted tree really is cut short here: what the cases must not read
    } finally {
      clock.mockRestore();
    }
  });
});
