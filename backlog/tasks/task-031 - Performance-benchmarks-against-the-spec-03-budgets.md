---
id: TASK-031
title: Performance benchmarks against the spec 03 budgets
status: To Do
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-09-26 20:07'
labels:
  - engine
  - ops
milestone: m-2
dependencies:
  - TASK-030
ordinal: 30000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
pytest-benchmark suite; bench workflow compares against main (performance-profiler).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 p95 search < 100 ms, match_ids with exclusions < 300 ms, 200-term expansion < 50 ms on the fixture
- [ ] #2 bench workflow fails on a >20% regression
- [ ] #3 Position-verified queries (stopword NEAR and wildcard phrases, e.g. the NEAR/5 the, "the*" NEAR/5 model) measured on the ~80k corpus against spec 03's exception for verified clauses, with results in the benchmark report
<!-- AC:END -->
