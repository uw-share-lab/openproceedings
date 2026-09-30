/**
 * Which wildcards each builder term holds, keyed as `/search` keys `query.expansions` (`<stem><op>`, the
 * normalized stem: `search.py` `expansions_json`), so a group can show its own terms' expansions after a
 * search (design B1, TASK-111). The stems are the server's: they come from its `ast` of the draft, never from
 * the term's text.
 */
import type { AstNode, CodePoints } from "./model";
import { spanOf } from "./read";

type Wildcard = Extract<AstNode, { kind: "wildcard" }>;

function wildcards(n: AstNode): Wildcard[] {
  switch (n.kind) {
    case "wildcard":
      return [n];
    case "phrase":
      return n.items.filter((i): i is Wildcard => i.kind === "wildcard");
    case "and":
    case "or":
      return n.children.flatMap(wildcards);
    case "not":
      return wildcards(n.child);
    case "near": // never inside a term (a NEAR doesn't fit), but this walks any ast
      return [...wildcards(n.left), ...wildcards(n.right)];
    default:
      return [];
  }
}

/** Per term id, the keys of the wildcards inside the term's span in the query `ast` was parsed from. */
export function termWildcards(ast: AstNode, spans: ReadonlyMap<number, CodePoints>): Map<number, string[]> {
  const all = wildcards(ast);
  const keys = new Map<number, string[]>();
  for (const [id, [from, to]] of spans) {
    const inside = all.filter((w) => spanOf(w)[0] >= from && spanOf(w)[1] <= to);
    if (inside.length > 0) keys.set(id, [...new Set(inside.map((w) => `${w.stem}${w.op}`))]);
  }
  return keys;
}
