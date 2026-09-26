---
name: field-weighted-bm25
description: The ranking standard — field-weighted BM25 (title 2.0, abstract 1.0, k1 1.2, b 0.75) that honestly approximates BM25F, ordering only inside the matched set, negations and filters never scoring, deterministic tie-break by id for every sort, and ranking params folded into index_version. Use when writing or reviewing engine/rank.py, boosts, sort options, pagination, or anything that claims ranking is reproducible.
---

# Field-weighted BM25 (spec 03 §Ranking, guarantee 5)

## The formula
`score(d) = 2.0 · BM25_title(d) + 1.0 · BM25_abstract(d)`, each per-field BM25 with **k1 = 1.2, b = 0.75**,
summed over the query's positive scoring clauses.

- This **approximates** BM25F. True BM25F combines weighted term frequencies across fields *before*
  saturation and uses one length normalisation. We score the fields separately and add the results. Docs,
  UI copy and the paper say "field-weighted BM25", never "BM25F".
- Boosts go on the per-field clauses from compile (`.claude/skills/ast-compilation/SKILL.md`). k1 and b may
  be fixed constants inside Tantivy. Verify this in the pinned version. If different values are ever needed,
  compute scores in `rank.py` rather than claim a setting that isn't applied.
- The weights are configuration, and the whole ranking config (weights, k1, b, sort definitions) is part of
  `ranking_params` in `index_version` (`.claude/skills/index-versioning/SKILL.md`). Changing a weight
  changes `index_version`.

## Membership is not ranking's business
- Ranking orders the matched set and nothing else. `total`, `match_ids` and exports are identical for
  every sort. Test: the union of all pages for each sort equals `match_ids`, with no duplicates and no gaps.
- **Negated clauses and filters contribute 0.** `MUST_NOT` doesn't score, and filters are constant-score or
  filter clauses. Adding `year:2024` or `NOT survey` must never reorder the documents that remain.
- Every wildcard expansion scores as its own term. A 200-term expansion is still only ordering.

## Sorts and determinism
| `sort` | Key |
|---|---|
| `relevance` (default) | `(-score, id)` |
| `year_desc` / `year_asc` | `(-year, id)` / `(year, id)` |
| `title` | `(display title casefolded, id)` |
| `semantic` | supplied by 06 when enabled; still tie-broken by `id` |

- The tie-breaker is **always `id`**. Tantivy's internal doc order depends on segments, so it is never a
  tie-breaker.
- Scores are compared as the exact floats Tantivy returns. Never round before sorting. Round only for
  display.
- `offset`/`limit` pagination is taken from the fully ordered list, so page 2 is stable across calls. When
  collecting top-k from Tantivy, include every document tied at the cut-off before applying the id
  tie-break, or page boundaries become nondeterministic.
- Determinism gate (07): same canonical query + `index_version` → identical order **and** scores.

## Gotchas
- BM25 statistics (doc frequency, average length) are index-wide, so adding records changes scores. That is
  why the snapshot hash is in `index_version`.
- The per-field sum rewards a term that appears in both fields. This is expected. Do not "fix" it by
  deduplicating terms.
- `ReferenceEngine` does not rank. Ranking tests compare Tantivy runs with each other (determinism), and
  with hand-computed scores on a tiny fixture.
