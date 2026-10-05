/**
 * Which `/search` group count belongs to each builder group (TASK-176; copy BD-12). The server counts each
 * concept group alone and sends its code-point span in the searched query (`groups.counts`, spec 04
 * §SearchResponse); a builder group is the count's when a term of it lies inside that span. Groups are
 * top-level parts of the query, so their spans never overlap and a term lies in at most one; "a term", not
 * "every term", because the canonical form writes a group that repeats one term (`(model OR model)`) as that
 * term, at the first one's span. A group written twice is one group there: the second shows no count.
 * (`backend/tests/contract/test_group_counts.py` holds the rule to the server's groups on every query of the
 * builder's read golden.) The spans are of the searched query, so the counts apply only while the draft is
 * that query (`countsFor`): a count is a fact about a query, and an edited draft is another query.
 */
import type { SearchResponse } from "@/components/search/use-search";
import type { Mode } from "@/lib/search-state";
import type { BuilderGroup, CodePoints } from "./model";

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

/** Per builder group id, the server's count of the group whose span holds a term of it. */
export function groupTotals(
  counts: GroupCounts["counts"],
  groups: readonly BuilderGroup[],
  spans: ReadonlyMap<number, CodePoints>,
): Map<number, number> {
  const totals = new Map<number, number>();
  for (const group of groups) {
    const terms = group.terms.flatMap((t) => {
      const span = spans.get(t.id);
      return span === undefined ? [] : [span];
    });
    const count = counts.find(({ span }) => {
      const [from, to] = [span[0] ?? 0, span[1] ?? 0];
      return terms.some(([s, e]) => s >= from && e <= to);
    });
    if (count !== undefined) totals.set(group.id, count.total);
  }
  return totals;
}
