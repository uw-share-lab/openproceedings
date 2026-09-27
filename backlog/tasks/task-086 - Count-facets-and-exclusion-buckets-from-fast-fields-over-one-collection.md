---
id: TASK-086
title: Count facets and exclusion buckets from fast fields over one collection
status: To Do
assignee: []
created_date: '2026-09-27 11:08'
labels:
  - engine
  - performance
milestone: m-3
dependencies: []
priority: high
ordinal: 84000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The /search endpoint's first page is over spec 03's 100 ms p95 at 80k. Measured (synthetic 80k index built as report_80k does; p95 CPU time of search.run(limit=50, facets=True, highlight=True), 30 runs, load 12-17): first page 136-238 ms for the nine non-empty Trust-Evals strings (main-1 214, main-3-sources 238, llm-as-judge 3), a later page 51-76 ms. Before the M3a review-gate fix (facets batched per kept set + the bounded faceted memo) the same numbers were 153-276 ms for every page.

Why: the cost is collecting the query, not the aggregations. At 80k one collection of main-1 costs ~31 ms whether it is a plain search, a count, one terms aggregation or four in one call (an all_query aggregation costs ~1 ms). A first page still collects the text query five times: the page (effective query), and four aggregates, one per distinct kept set (effective for venue+year; without the track default for track; without the status default for status and exclusion accounting's status count; identified for exclusion accounting's track count). Highlighting adds ~35 ms.

Structural fix: collect the query without its top-level filter conjuncts once, read venue/year/track/status from their fast columns for every hit, and evaluate each top-level Filter / NOT Filter conjunct in Python per document; every disjunctive facet and both exclusion buckets are then counts over that one collection. Filters are ConstScore 0.0, so the effective query's scores are the base query's scores on the documents that pass (the page could come from the same collection). Expected first page ~2 collections + highlights (~100 ms at 80k), so measure.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Every disjunctive facet and exclusion bucket comes from one collection of the query without its top-level filters (plus the page's collection, unless it is shared too)
- [ ] #2 backend/tests/differential and test_exclusions stay green: no count or ID set changes
- [ ] #3 report_80k's /search first-page column is under 100 ms p95 CPU for every Trust-Evals string at 80k, or spec 03 records the measured exception
<!-- AC:END -->
