import { describe, expect, it } from "vitest";
import golden from "./lexer-golden.json";
import { lexemes } from "./lex";

// Every backend lexer/parser golden input, error and warning input, the Trust-Evals strings and the probes:
// the highlighter's lexemes are the server lexer's, class for class and span for span (code points).
describe("lexemes agree with backend/src/openproceedings/query/lexer.py", () => {
  it("covers a real set of inputs", () => {
    expect(golden.cases.length).toBeGreaterThan(300);
  });

  it.each(golden.cases.map((c) => [JSON.stringify(c.q).slice(0, 80), c] as const))("%s", (_name, c) => {
    expect(lexemes(c.q)).toEqual(c.tokens);
  });
});
