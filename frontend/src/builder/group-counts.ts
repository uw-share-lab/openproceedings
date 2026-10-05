/**
 * Which `/search` group count belongs to each builder group (TASK-176; copy BD-12). The server counts each
 * concept group alone and sends its code-point span in the searched query (`groups.counts`, spec 04
 * §SearchResponse); a builder group is the count's when a term of it lies inside that span. Groups are
 * top-level parts of the query, so their spans never overlap and a term lies in at most one; "a term", not
 * "every term", because the canonical form writes a group that repeats one term (`(model OR model)`) as that
 * term, at the first one's span. A group written twice is one group there: the second says "same as group N".
 * (`backend/tests/contract/test_group_counts.py` holds the rule to the server's groups on every query of the
 * builder's read golden.) The spans are of the searched query, so the counts apply only while the draft is
 * that query (`countsFor`): a count is a fact about a query, and an edited draft is another query.
 */
import type { SearchResponse } from "@/components/search/use-search";
import type { Mode } from "@/lib/search-state";
import type { AstNode, BuilderGroup, CodePoints } from "./model";
import { spanOf } from "./read";

/** `/search`'s `groups`, as the typed client returns it (a span is `number[]`). */
export type GroupCounts = SearchResponse["groups"];

/** The last answered `/search`: its query, its `total` and its `groups`. */
export interface SearchedGroups {
  readonly q: string;
  readonly mode: Mode;
  readonly total: number;
  readonly groups: GroupCounts;
}

/** `searched` if it is the search of this draft, else null: no count is shown for another query. */
export function countsFor(
  searched: SearchedGroups | null | undefined,
  text: string,
  mode: Mode,
): SearchedGroups | null {
  return searched != null && searched.q === text && searched.mode === mode ? searched : null;
}

/** What a builder group shows: its two counts, or the earlier group (1-based) it repeats. */
export type GroupShown =
  | { readonly kind: "counted"; readonly total: number; readonly totalWithout: number }
  | { readonly kind: "same"; readonly as: number };

type Leaf = Extract<AstNode, { kind: "term" | "wildcard" | "phrase" }>;

/** Every term, wildcard and phrase of `ast`, by its span (`"start,end"`). */
function leavesBySpan(ast: AstNode, into = new Map<string, Leaf>()): Map<string, Leaf> {
  switch (ast.kind) {
    case "term":
    case "wildcard":
    case "phrase":
      into.set(spanOf(ast).join(","), ast);
      break;
    case "and":
    case "or":
      for (const child of ast.children) leavesBySpan(child, into);
      break;
    case "not":
      leavesBySpan(ast.child, into);
      break;
    case "near":
      leavesBySpan(ast.left, into);
      leavesBySpan(ast.right, into);
      break;
    default:
      break;
  }
  return into;
}

/** A node as the server compares two of them: everything but where it was written. */
const meaning = (node: unknown): string =>
  JSON.stringify(node, (key: string, value: unknown) => (key === "span" ? undefined : value));

/**
 * What a group means to the server, which holds two groups that mean the same once: its terms as the
 * server's `ast` reads them (normalised tokens, stems and scopes, never the typed text), each once, in order
 * (the canonical form: an OR's repeated branches are one). Null when a term has no leaf in `ast`.
 */
function groupMeaning(
  group: BuilderGroup,
  spans: ReadonlyMap<number, CodePoints>,
  leaves: ReadonlyMap<string, Leaf>,
): string | null {
  const terms: string[] = [];
  for (const t of group.terms) {
    const leaf = leaves.get(spans.get(t.id)?.join(",") ?? "");
    if (leaf === undefined) return null;
    const m = meaning(leaf);
    if (!terms.includes(m)) terms.push(m);
  }
  return terms.length === 0 ? null : JSON.stringify(terms);
}

/**
 * Per builder group id, the server's counts of the group whose span holds a term of it. A group with none
 * that means what an earlier counted group means (`groupMeaning`, read from the server's `ast` of the query:
 * the server's own rule for "the same group", not a comparison of typed text) is that group to the server,
 * which holds it once: it says so rather than showing nothing.
 */
export function groupTotals(
  counts: GroupCounts["counts"],
  groups: readonly BuilderGroup[],
  spans: ReadonlyMap<number, CodePoints>,
  ast: AstNode | null = null,
): Map<number, GroupShown> {
  const shown = new Map<number, GroupShown>();
  const leaves = ast === null ? new Map<string, Leaf>() : leavesBySpan(ast);
  const counted = new Map<string, number>(); // a counted group's meaning → its number
  groups.forEach((group, index) => {
    const terms = group.terms.flatMap((t) => {
      const span = spans.get(t.id);
      return span === undefined ? [] : [span];
    });
    const count = counts.find(({ span }) => {
      const [from, to] = [span[0] ?? 0, span[1] ?? 0];
      return terms.some(([s, e]) => s >= from && e <= to);
    });
    const key = groupMeaning(group, spans, leaves);
    if (count !== undefined) {
      shown.set(group.id, { kind: "counted", total: count.total, totalWithout: count.total_without });
      if (key !== null && !counted.has(key)) counted.set(key, index + 1);
      return;
    }
    const as = key === null ? undefined : counted.get(key);
    if (as !== undefined) shown.set(group.id, { kind: "same", as });
  });
  return shown;
}
