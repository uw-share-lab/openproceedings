---
id: TASK-196
title: >-
  Group counts push a cold first page of a wildcard-phrase query over the 100 ms
  p95 budget
status: To Do
assignee: []
created_date: '2026-10-05 13:59'
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
<!-- AC:END -->
