---
id: TASK-166
title: >-
  Let exclusion-only callers skip the facet-combination aggregation (TASK-088
  deferral)
status: In Progress
assignee: []
created_date: '2026-10-02 09:27'
updated_date: '2026-10-03 01:26'
labels:
  - engine
  - performance
  - deferred
dependencies: []
references:
  - backend/src/openproceedings/engine/exclusions.py
  - backend/tests/bench/test_bench.py
priority: low
ordinal: 136000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Source: TASK-088, PR #6 bench note, deferred. Exclusion accounting reads its buckets from the same facet-combination aggregation as the sidebar facets, so a caller that needs only the exclusion counts (an export, a record save, `op search` without facets) still pays for every facet combination. PR #6's bench measured tests/bench/test_bench.py::test_match_ids_with_exclusions_on_a_broad_query at about 1.46 ms before and 1.91 ms after (+31%, 5k fixture). The full /search aggregation is about 37 ms median CPU at 80k (TASK-088 notes). Add a path that computes only the exclusion buckets for those callers. Not needed for the 100 ms budget, which TASK-088 met in wall time; this is CPU headroom.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 test_match_ids_with_exclusions_on_a_broad_query is back to about its pre-PR #6 time (about 1.46 ms on the 5k fixture), with the before/after numbers in docs/results/
- [x] #2 Exclusion counts are identical to the facet path for every Trust-Evals string (test_facets_equal or a new equality test); no ID set or count changes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Preserve exclusion narrowing and broad COMBO coverage; validate identical counts against oracle/generated trees; measure COMBO versus ORDER on quiet paired runs; document changed cold-cache method; run full stable test/lint/tooling, then complete via CLI.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Recovery restored original broad COMBO benchmark and added separate ORDER benchmark. Shared-lock alternating 5k200 run, load3.2, broad warm wall/CPU p50 1.5ms COMBO versus0.6ms ORDER,1080 versus45 combos; every protocol string and broad-query exclusion result equal before timing. Focused engine/facet/benchmark checks99passed85.49s. Current schema-3 full80k report every budgeted number within budget (CPU-idle-qualified baseline explicitly documented, with memory-pressure limitations). Fresh evidence docs/results/2026-10-02-perf-recovery.md; older cold reports retained caches and are not directly comparable. Full stable suite pending after reversible CLI history reconstruction; no real data writes.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Exclusion-only callers aggregate ORDER(track,status); all-facet callers retain COMBO. Separate broad benchmarks preserve coverage; paired broad5k median1.5ms versus0.6ms with equal counts. Fresh schema-3 report within budget under recorded conditions. Full stable checks pending before terminal status.
<!-- SECTION:FINAL_SUMMARY:END -->
