---
id: TASK-196
title: >-
  Group counts push a cold first page of a wildcard-phrase query over the 100 ms
  p95 budget
status: To Do
assignee: []
created_date: '2026-10-05 13:59'
updated_date: '2026-10-05 14:37'
labels:
  - perf
  - search
milestone: m-3
dependencies: []
ordinal: 140000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
docs/results/2026-10-05-bench-group-counts.md (index fd13d8d27535, 200 rounds, load under 10): the first page of the Trust-Evals wildcard-phrase LLM query with group counts has p95 110.8 ms (median 80.2 ms) against spec 03's 100 ms budget, measured with the facet memo cleared every round; later pages cost the same with or without counts. Found by the review gate's performance-profiler round (PERF-S2) on 2026-10-05.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The cold first page of every Trust-Evals string with default group counts is under the 100 ms p95 budget on the current index, measured as in the bench doc; or the budget's treatment of the cold group-count case is decided and recorded with the measurement
- [ ] #2 Re-measured with group_counts_report.py at a sustained 1-minute load under 5 (the load at the start and the end both under 5, as the bench doc records it), and spec 03's 'Exception, as measured (TASK-196)' bullet and spec 04's Cost figures updated from that run or removed
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-05 (gate round 2, PERF-R2-1/DOC-R2-S3): spec 03 §Performance budgets now carries 'Exception, as measured (TASK-196)' for this miss; spec 04 §SearchResponse Cost and docs/results/2026-10-05-bench-group-counts.md cite this task. The bench's timed /search rows now assert that no measured round skipped its counting (PERF-R2-N c).
<!-- SECTION:NOTES:END -->
