---
id: TASK-024
title: AST → Tantivy compilation
status: Done
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-09-26 20:08'
labels:
  - engine
milestone: m-2
dependencies:
  - TASK-023
  - TASK-016
ordinal: 23000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Spec 03 §AST → Tantivy compilation (ast-compilation skill).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Phrases never cross fields; NOT without a positive clause gets an explicit all-docs clause
- [x] #2 Wildcards expand via the term dictionary; list returned; >200 is an error
- [x] #3 NEAR multi-token fallback verifies positions; filters are non-scoring
- [x] #4 op search --explain prints the compiled query
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented in engine/compile.py (AST -> Tantivy; independent of ReferenceEngine) and engine/tantivy_engine.py (TantivyEngine: term-dictionary expansion with the 200 cap before compiling, match sets via an ord fast column + ids.txt added to the index, disjunctive facets by terms aggregation, explain), plus op search --explain / --ids. Slop measured on tantivy 0.26.2: in-order <= n between, reversed costs 2, [a,a] at slop>=1 matches one occurrence, so a NEAR a and phrase/wildcard operands take the position-verified fallback. Filters are const-score 0 (scores unchanged, tested). Verified: 44 golden queries on the 200-record fixture, a row per table line and gotcha vs ReferenceEngine, combination property vs the oracle, and locally the ten Trust-Evals protocol strings on the real corpus (0 differences; 1-10 ms vs 130-1000 ms). search() returns id order until task-025.

Review round (2026-09-26): 0 set differences in 2,000 generated ASTs and crafted cases (reviewer). Fixed: op search refuses an over-cap wildcard (EngineError) instead of a traceback; verified fallback uses positions maps + binary search (80k worst cases 22.7->2.0 s, 28.4->3.6 s, 83.6->10.7 s; facets 25->1.8 s via a compile cache); NOT's all-docs clause const-score 0; wildcards as SHOULD of term queries (scored per term); candidate items deduped; --index prefers <data-dir>/indexes and a missing index says how to build one; test logger reset after every test (conftest); rows for flattening, adjacency, scoring, CLI; no assume(). Rejected: a hard cap on verified candidates (it would refuse valid queries; cost is linear and measured, budgeted in task-031). Spec 08 / exactness-guardian mark --engine reference as task-030.

Verification round (2026-09-26): 0 membership differences (300k random position checks, 2.5k generated queries). Fixed: verified clauses memoised per engine and field (facets after a match 0.1-0.3 s on 80k, were 10.6-32.6 s with default filters; the earlier '25 -> 1.8 s' held only without filters); candidates drop items implied by narrower ones ('trust trust*' scores trust once); op search parses first, logs a missing index as cli_refused, documents --index precedence (tested). Candidate cap rejected because a cap would make results depend on corpus size and break search-record replay; spec 03 records the exception for verified clauses, and task-031 gained an AC to measure them on 80k.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
AST -> Tantivy compilation (engine/compile.py) and TantivyEngine (engine/tantivy_engine.py), with op search --explain / --ids: exact per-field terms, phrases and slop-NEAR (slop measured), wildcards from the term dictionary as scored ORs, non-scoring filters and NOT, and a memoised position-verified fallback for the rest. Verified: 44 golden queries, a row per compilation-table line vs ReferenceEngine, combination properties, two review rounds (0 membership differences over 2k+ generated ASTs and 300k random position checks), mutation passes, and locally the ten Trust-Evals strings on the real corpus.
<!-- SECTION:FINAL_SUMMARY:END -->
