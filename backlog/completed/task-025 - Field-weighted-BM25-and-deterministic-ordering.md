---
id: TASK-025
title: Field-weighted BM25 and deterministic ordering
status: Done
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-09-26 20:39'
labels:
  - engine
milestone: m-2
dependencies:
  - TASK-024
ordinal: 24000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Spec 03 §Ranking (field-weighted-bm25 skill).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 title 2.0 / abstract 1.0, k1 1.2, b 0.75; params in index_version
- [x] #2 All sorts tie-break by id; same query + index → identical order and scores
- [x] #3 Negations and filters never score
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented: per-field BoostQuery weights (title 2.0, abstract 1.0) from the manifest's ranking_params; k1/b are Tantivy's constants (1.2/0.75), confirmed by a hand-computed score; ranked(ast, sort) orders the full match set by (-score, id), (-year, id), (year, id) or (casefolded title via a title_rank fast column, id), independent of Tantivy's hit order; search pages it; sort definitions added to ranking_params (index ids change). Filters, NOT and verified id checks score 0 (tested: they never reorder or rescore what remains). Verified clauses score as their distinct items' per-field BM25. Tests: hand-computed BM25, title = 2x abstract, identical order and exact scores across two builds for every sort, page unions = match_ids, id tie-breaks, reversed hit order, sort keys, bad sort.

Review fixes: every Boolean of three or more clauses is a balanced binary tree (compile.combine), because Tantivy's union reorders summation after a term runs out (swap_remove per 4,096-doc window), leaving identical texts an ulp apart and their order layout-dependent (tested across the 4,096 boundary and on a multi-segment build vs one segment; the flat-union mutant is killed). SCHEMA_VERSION 2 (ord and title_rank columns); the engine refuses an index with another schema/tokenizer version or a bm25 Tantivy doesn't apply. The title sort key is casefold(NFKC(display title)), ranked at build in a binary pre-pass. search takes the top offset+limit by heapq. index_version defaults are read at call time. build_index(commit_every=) makes multi-segment test builds. Docs: rank.py references removed (ranking lives in tantivy_engine.py), spec 00 says field-weighted BM25.

Verification round (all 7 findings confirmed fixed) raised 1 should + 4 nits, all fixed: title-key wording is casefold(NFKC(display title)) in both skills and the index.py comment; test_compile checks that no compiled Boolean has more than two clauses (kills the flat-AND mutant, which no score probe showed drifting); the segment test is no longer described as the flat-union guard (the 4,300-doc window test is); combine([]) raises ValueError; the engine refuses an index built by another tantivy_version, and a test pins the installed Tantivy to TANTIVY_PINNED (0.26.2), the version TANTIVY_BM25 was confirmed on.
<!-- SECTION:NOTES:END -->
