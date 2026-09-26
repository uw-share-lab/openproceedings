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
| `Near(a, b, n)`, single-token operands | per field: `PhraseQuery([a,b], slop) OR PhraseQuery([b,a], slop)` | unordered; ≤ n intervening words |
| `Near` with a multi-token operand | candidate filter: `MUST a MUST b` in the same field, then verify positions in Python | documented fallback; verification re-normalizes the stored text with `normalize.py` |
| `Wildcard w` | `Boolean(SHOULD term…)` of the expanded terms, per field | expansion from the term dictionary, returned to the caller (`.claude/skills/wildcards-and-expansion/SKILL.md`) |
| `And` / `Or` | `BooleanQuery` MUST / SHOULD | |
| `Not x` | `Boolean(MUST all_docs, MUST_NOT x)` | see gotcha 1 |
| `Filter` | `TermQuery`/`RangeQuery` on fast fields, non-scoring | `venue:` value mapped to the stored spelling |

## Gotchas
1. **A Boolean query with only MUST_NOT clauses matches nothing in Tantivy.** `a OR NOT b` means
   a ∪ (corpus − b). Compile every `Not` with an explicit all-docs positive clause, or restructure it under
   an enclosing `And`. The parser rejects all-negative *queries*, but nested negations are legal.
2. **Slop is not NEAR/n until a test says so.** Check against the oracle whether a Tantivy slop value of `n`
   means "≤ n intervening positions" for an in-order pair, and how reversed order is costed, in the pinned
   version. Pin the mapping in `compile.py` with golden cases at n = 0, 1 and n+1, in both orders.
3. `NEAR` of a term with itself (`a NEAR/2 a`) needs two distinct occurrences. Add a golden case.
4. Filters must not score. Wrap them as a constant-score or filter clause (verify the tantivy-py API), so
   adding `year:2024` never reorders results (`.claude/skills/field-weighted-bm25/SKILL.md`).
5. Empty expansion compiles to a match-nothing clause, never to a dropped clause. A dropped clause in an
   `And` widens the result set.
6. Default filters arrive already explicit in the AST (`.claude/skills/default-filters/SKILL.md`). Compile
   never adds them.

## `op search --explain`
`--explain` prints, in order: the input, the canonical string, the warnings and translations, the wildcard
expansions, the compiled query rendered as a readable tree (field, clause kind, slop, boost, and whether it
is a filter), and which NEAR clauses took the verification fallback. `--engine reference|tantivy` picks the
engine, and `--ids` prints the sorted ID set. Every differential counterexample is reported with this output.

## Review checklist
- [ ] every row has a golden case in `backend/tests/golden/`, run through both engines
- [ ] no clause type reaches a field other than title/abstract unless it is an explicit filter
- [ ] explain output updated for any new clause kind
