---
id: TASK-088
title: >-
  Headroom for the /search first page at 80k: non-ASCII tokenizer fast path,
  real-corpus re-measure
status: To Do
assignee: []
created_date: '2026-09-27 11:38'
updated_date: '2026-09-27 16:20'
labels:
  - engine
  - performance
milestone: m-4
dependencies:
  - TASK-086
priority: medium
ordinal: 86000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
After task-086 a /search first page (search.run(limit=50, facets=True, highlight=True)) on the synthetic 80k index cost 75-117 ms p95 CPU (main-1 117 ms, main-3-sources 109 ms). Breakdown of main-1 (median CPU): page collection 34 ms, the base's facet-combo aggregation 37 ms, highlighting 50 hits 33 ms (almost all query/normalize.py _tokenize_each_char: the synthetic generator's text is ~50% non-ASCII and misses the ASCII fast path, real abstracts ~23%), Python facet/exclusion counting 3 ms, display 1 ms. Two collections of the text query are the floor of an exact design (the page needs the effective query's own scores; reusing the base collection's scores is not provably bit-identical, because compile.combine groups the conjuncts differently once filters join), and facets need the base.

Done in the M3a review gate round 2 (option 1): search.run compiles the effective tree in the request's thread (cold verified clauses take their verification slot there), then runs the facet aggregation on a worker thread overlapping the page collection, display and highlighting (Tantivy releases the GIL). Output identical to the sequential path (tests/unit/test_search_overlap.py; tests/contract/test_search_overlap.py). Wall p95 over 200 runs at 80k: 57-85 ms for every non-empty Trust-Evals string (main-1 84.5 ms), CPU per request unchanged 74-109 ms (docs/results/2026-09-27-search-overlap.md). The budget is met in wall time; CPU per request, which bounds throughput, is not reduced.

What remains is headroom, for M4: (2) a tokenizer fast path for non-ASCII Latin text (query/ owners; needs the frozen-copy parity test and no TOKENIZER_VERSION change), which cuts highlighting CPU; (3) re-measure on the real corpus once M4 lands, where highlighting is cheaper.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The /search first page is under 100 ms wall p95 at 80k for every Trust-Evals string, measured the way report_80k's /search columns measure it (wall time, at least 100 rounds), or spec 03 records the exception with numbers
- [x] #2 No ID set, score, facet or exclusion count changes (differential, golden, test_facets_equal, test_search_overlap)
- [ ] #3 A non-ASCII Latin fast path in query/normalize.py tokenize, pinned to the frozen copy (no TOKENIZER_VERSION bump), measured in CPU per request
- [ ] #4 report_80k's /search columns re-measured on the real M4 corpus, on a quiet machine, and spec 03's Measured updated
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
PR #6 bench (advisory): test_match_ids_with_exclusions_on_a_broad_query min +31% vs dev on the 5k fixture (~1.46 → 1.91 ms), because exclusion accounting now uses the one combos collection (TASK-086). Option: let exclusion-only callers (op search without facets) skip the combos aggregation.
<!-- SECTION:NOTES:END -->
