import { describe, expect, it } from "vitest";
import { readGolden } from "./golden";
import { modelOf, readAst, sourceSpans } from "./read";
import { termWildcards } from "./expansions";

const cases = readGolden();

/** Each term's written text and its wildcards' `/search` keys, for a native golden query that fits. */
function keysOf(q: string): [string, readonly string[]][] {
  const c = cases.find((x) => x.q === q && x.mode === "native");
  if (c?.ast == null) throw new Error(`no native golden case ${q}`);
  const reading = readAst(c.ast);
  if (reading.kind !== "fits") throw new Error(`${q} doesn't fit`);
  const model = modelOf(q, reading.shape);
  const keys = termWildcards(c.ast, sourceSpans(model, reading.shape));
  return [...model.groups, ...(model.exclude === null ? [] : [model.exclude])].flatMap((g) =>
    g.terms.map((t) => [t.text, keys.get(t.id) ?? []] as [string, readonly string[]]),
  );
}

describe("termWildcards: each term's wildcards, keyed as /search keys expansions (TASK-111)", () => {
  it("keys a wildcard by its normalized stem and operator; a plain term has none", () => {
    expect(
      keysOf('("foundation model" OR LLM) AND (trustworth* OR trust) AND benchmark AND venue:ICLR'),
    ).toEqual([
      ['"foundation model"', []],
      ["LLM", []],
      ["trustworth*", ["trustworth*"]],
      ["trust", []],
      ["benchmark", []],
    ]);
  });

  it("finds a wildcard inside a phrase, and in the Exclude row", () => {
    expect(
      keysOf('("x" OR model$ OR model$) -title:(“vision language” | “vision language” | gpt-4*)'),
    ).toEqual([
      ['"x"', []],
      ["model$", ["model$"]],
      ["model$", ["model$"]],
      ["“vision language”", []],
      ["“vision language”", []],
      ["gpt-4*", ["4*"]],
    ]);
  });
});
