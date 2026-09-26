---
id: TASK-024
title: AST → Tantivy compilation
status: In Progress
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-09-26 19:29'
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
<!-- SECTION:NOTES:END -->
