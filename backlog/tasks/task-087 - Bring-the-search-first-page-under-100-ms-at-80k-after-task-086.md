---
id: TASK-087
title: Bring the /search first page under 100 ms at 80k after task-086
status: To Do
assignee: []
created_date: '2026-09-27 11:32'
labels:
  - engine
  - performance
milestone: m-3
dependencies:
  - TASK-086
priority: high
ordinal: 85000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
After task-086 a /search first page (search.run(limit=50, facets=True, highlight=True)) on the synthetic 80k index costs, p95 CPU over 30 runs (load 7-19): main-1 117 ms, main-3-sources 109 ms, the other non-empty Trust-Evals strings 75-93 ms. Breakdown of main-1 (median CPU): page collection 34 ms, the base's facet-combo aggregation 37 ms, highlighting 50 hits 33 ms (almost all query/normalize.py _tokenize_each_char: the synthetic generator's text is ~50% non-ASCII and misses the ASCII fast path, real abstracts ~23%), Python facet/exclusion counting 3 ms, display 1 ms. Two collections of the text query are the floor of an exact design: the page needs the effective query's own scores (reusing the base collection's scores is not provably bit-identical, because compile.combine groups the conjuncts differently once filters join), and facets need the base. Options, to decide: (1) overlap the combo aggregation with the page collection in search.run (tantivy-py releases the GIL: two threads ran two collections in half the wall time), cutting wall latency by ~35 ms but not CPU, and interacting with the cold-verification semaphore; (2) a tokenizer fast path for non-ASCII Latin text (query/ owners; needs the frozen-copy parity test and no TOKENIZER_VERSION change); (3) measure on the real corpus once M4 lands, where highlighting is cheaper.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The /search first page is under 100 ms p95 at 80k for every Trust-Evals string, measured the way report_80k's /search column measures it, or spec 03 records the exception with numbers
- [ ] #2 No ID set, score, facet or exclusion count changes (differential, golden, test_facets_equal)
<!-- AC:END -->
