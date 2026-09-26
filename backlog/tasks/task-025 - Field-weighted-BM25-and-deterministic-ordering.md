---
id: TASK-025
title: Field-weighted BM25 and deterministic ordering
status: In Progress
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-09-26 20:12'
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
<!-- SECTION:NOTES:END -->
