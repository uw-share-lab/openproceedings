---
name: ast-compilation
description: The AST → Tantivy compilation table for engine/compile.py — per-field term and phrase queries that never cross fields, NEAR via slop plus the position-verified fallback for multi-token operands, wildcards as explicit OR of expanded terms, NOT without a positive clause, filters as non-scoring fast-field queries, and the `op search --explain` rendering. Use when writing or reviewing engine/compile.py or tantivy_engine.py, or debugging a differential counterexample.
---

# AST → Tantivy compilation (spec 03 §AST → Tantivy compilation)

We never use Tantivy's query parser. `engine/compile.py` turns the 02 AST into Tantivy query objects. The
definition of correct is `ReferenceEngine` (`.claude/skills/reference-oracle/SKILL.md`), not Tantivy's
documentation.

## Table
| AST | Tantivy | Notes |
|---|---|---|
| `Term t`, no field | `Boolean(SHOULD title:t, SHOULD abstract:t)` | |
| `Term t`, `title:`/`abstract:` | `TermQuery` on that field | |
| Term normalizing to >1 token (`vision-language`) | as `Phrase` of those tokens | never an AND of the parts |
| `Phrase p` | `PhraseQuery(title, p) OR PhraseQuery(abstract, p)` | **never** across fields; field-scoped phrases → one side only |
| `Near(a, b, n)`, two **different** single terms | per field: `PhraseQuery([a,b], slop=n) OR PhraseQuery([b,a], slop=n)` | unordered; ≤ n intervening words (measured, see gotcha 2) |
| `Near` with a phrase or wildcard operand, or a term with itself; a phrase with a wildcard item | candidate filter: every item `MUST` in the same field, then positions verified in Python over the candidates' stored token streams (the indexed text split on spaces); the verified ids become a `TermSetQuery` on `id`, kept with the candidate query for scoring | the documented fallback; `--explain` lists each verified clause |
| `Wildcard w` | `Boolean(SHOULD term…)` of the expanded terms, per field (never a `TermSetQuery`, which scores every match 1) | expansion from the term dictionary, returned to the caller (`.claude/skills/wildcards-and-expansion/SKILL.md`); scores exactly as the explicit OR of its terms (tested) |
| `And` / `Or` | `BooleanQuery` MUST / SHOULD | |
| `Not x` | `Boolean(MUST ConstScore(all_docs, 0), MUST_NOT x)` | see gotcha 1; the all-docs clause adds no score (`AllQuery` scores 1, which under an OR would lift some documents) |
| `Filter` | `TermQuery`/`RangeQuery` on fast fields, non-scoring | `venue:` value mapped to the stored spelling |

## Gotchas
1. **A Boolean query with only MUST_NOT clauses matches nothing in Tantivy.** `a OR NOT b` means
   a ∪ (corpus − b). Compile every `Not` with an explicit all-docs positive clause, or restructure it under
   an enclosing `And`. The parser rejects all-negative *queries*, but nested negations are legal.
2. **Slop, measured on tantivy 0.26.2:** an in-order pair at slop n matches ≤ n tokens between; a reversed
   pair costs 2 more, so the reversed matches slop admits are within NEAR/n anyway and
   `[a,b] OR [b,a]` at slop n is exact. Pinned by golden rows at n = 0, 1, 2 and n+1, both orders
   (`test_compile.py`).
3. `NEAR` of a term with itself needs two distinct occurrences, but `[a,a]` at slop ≥ 1 also matches a
   single `a` (measured), so it always takes the verified fallback (golden rows `alpha NEAR/1 alpha`,
   `NEAR/0`).
4. Filters must not score. Wrap them as a constant-score or filter clause (verify the tantivy-py API), so
   adding `year:2024` never reorders results (`.claude/skills/field-weighted-bm25/SKILL.md`).
5. Empty expansion compiles to a match-nothing clause, never to a dropped clause. A dropped clause in an
   `And` widens the result set.
6. Default filters arrive already explicit in the AST (`.claude/skills/default-filters/SKILL.md`). Compile
   never adds them.

## As built
`backend/src/openproceedings/engine/compile.py` (the table; shares no matching code with ReferenceEngine)
and `engine/tantivy_engine.py` (`TantivyEngine`: expansion from the term dictionary via
`terms_with_prefix` over both fields, the 200 cap before compiling; match sets read back through the
`ord` fast column and `ids.txt`; disjunctive facets by a terms aggregation; ranking per the field-weighted-bm25 skill). Every Boolean of
three or more clauses (And/Or children, the per-field OR, year ranges, wildcard expansions, verified
candidates) goes through `combine`, a balanced binary tree, so identical texts score identically. Filters are `ConstScoreQuery(…, 0.0)`: they never change a score
(tested). The verified fallback finds each operand's occurrences from a token→positions map and pairs NEAR
operands by binary search (each operand's width is fixed), so its cost is linear in the candidates' text:
on a synthetic 80k index stopword cases take 2.3–3.3 s cold and the wildcard-phrase string `main-2-pop`
10.1 s (`docs/results/2026-09-27-bench.md`); its candidate
query holds each distinct item once, so a repeated term isn't scored twice. `facets` compiles each distinct
filter-free query once, and the engine memoises every verified clause (per field), so facets after a match
cost 0.1–0.3 s on 80k. `facets` collects the query once, without its top-level facet-field filters (`Filter` or
`NOT` of one; the *base*), as counts per (venue, year, track, status) from one nested terms aggregation (text
fast columns can't be read per document in tantivy-py), then counts every field in Python: a combo counts for
F when it passes every set-aside filter not on F (task-086; equal to one collection per kept set and to the
oracle, `test_facets_equal.py`). The combos are memoised per base (`faceted`, keyed by its span-less, sorted
conjuncts), so exclusion accounting, later pages and queries differing only in filters never collect again.
The memos (`compiled`, `verified`, `expanded`, `faceted`) are bounded by what they hold, not
by entry count (one verified clause can hold every id): `TantivyEngine.MAX_VERIFIED_IDS`, `MAX_EXPANDED_TERMS`,
`MAX_COMPILED_UNITS` and `MAX_FACET_COMBOS` budget the ids/terms charged to each, and a memo is cleared once its append-only ledger
(`charges`, summed incrementally; `_trim`) passes its budget — every race over-counts, never under
(`tests/unit/engine/test_memo_budget.py`). They are
shared by the API's thread pool with no lock (task-080): read an entry with one `.get()`, never `in` then
`[key]` (another thread may clear the memo between them), and store an entry only once it is complete. Every
value is a pure function of its key and the immutable index, so a clear or a lost race only recomputes the
same value (`tests/unit/engine/test_concurrency.py`). Only single dict operations are assumed atomic (true under
the GIL and on free-threaded 3.13t), so never iterate a memo or check-then-act across two operations. Candidates hold each distinct item once, and an item implied by a narrower one
(`trust` implies `trust*`) is dropped, so no term is scored twice; that is how a verified clause scores
(field-weighted-bm25 skill). Spec 03 records the budget exception for verified clauses. Checked: the 44 golden queries of the 200-record fixture, a row per table line against
ReferenceEngine, and (locally) the ten Trust-Evals protocol strings on the real corpus, identical sets.

## `op search --explain`
`op search <q> --explain` prints, in order: the input, the warnings and translations, the canonical string
(the effective query, default filters included), the index_version, the compiled query as a readable tree
(field, clause kind, slop, and whether it is a filter), the wildcard expansions, and which clauses took the
verification fallback. `op search <q> --ids` prints the sorted id set. Both take `--index` (a directory or
an index_version; default `indexes/current`) and `--mode native|scholar`; as built (task-030), ranked output
by default, and `--ids --engine reference` runs the oracle over the index's snapshot. Every differential counterexample is reported with this output.

## Review checklist
- [ ] every row has a golden case in `backend/tests/golden/`, run through both engines
- [ ] no clause type reaches a field other than title/abstract unless it is an explicit filter
- [ ] explain output updated for any new clause kind
