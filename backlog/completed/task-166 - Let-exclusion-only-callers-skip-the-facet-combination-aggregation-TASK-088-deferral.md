---
id: TASK-166
title: >-
  Let exclusion-only callers skip the facet-combination aggregation (TASK-088
  deferral)
status: Done
assignee: []
created_date: '2026-10-02 09:27'
updated_date: '2026-10-03 01:33'
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
Exclusion-only callers aggregate track/status (ORDER); sidebar callers retain full COMBO. The original broad COMBO benchmark is restored and the ORDER caller has a separate benchmark. Fresh alternating 5k run (200 rounds, load 3.2) gave broad warm wall/CPU p50 1.5 ms COMBO versus 0.6 ms ORDER, with 1,080 versus 45 combos and exactly equal exclusion counts for every protocol string and the broad query. COMBO remains about the historic 1.46 ms target; no speedup is attributed to its unchanged all-facet scope.

Focused schema/facet/benchmark checks: 99 passed in 85.49 s. Fresh default schema-3 80k report: every budgeted number within budget, with CPU-idle-qualified baseline and memory-pressure limits recorded. Cold runs reset every engine memo including ordinal lookup; older cold columns retained caches and are not comparable. Evidence: docs/results/2026-10-02-perf-recovery.md and 2026-10-02-schema-3-bench.md.

Stable f2b50e3c, shared heavy lock, Node 22.23.3, PYTEST_XDIST_AUTO_NUM_WORKERS=4: make test passed (backend 6330 passed, 2 skipped in 137.52 s; frontend 3209 passed, 40 files in 6.30 s); make lint passed; make tooling passed (49 agents, 53 skills, 17 commands, zero errors, all case tables passed). HEAD and clean tree unchanged throughout. No real data modified.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Exclusion-only callers count ORDER (track/status), with equal results and separate COMBO/ORDER benchmarks. Quiet broad 5k warm median 1.5 ms versus 0.6 ms, 1,080 versus 45 combos. Fresh schema-3 report and full make test/lint/tooling pass; source and measured conditions documented in docs/results/2026-10-02-perf-recovery.md.
<!-- SECTION:FINAL_SUMMARY:END -->
