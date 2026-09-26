---
id: TASK-076
title: Headroom for warm searches over wildcard phrases at 80k
status: To Do
assignee: []
created_date: '2026-09-26 23:03'
labels:
  - engine
  - performance
milestone: m-4
dependencies:
  - TASK-031
ordinal: 74000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
task-031: on a quiet M-series Mac with the synthetic 80k corpus, main-2-pop (wildcard phrases such as model$, position-verified, all clauses cached) searches warm at median 61 ms, p95 95 ms, p99 148 ms over 200 runs, against spec 03's 100 ms p95 for a 50-hit search. Within budget, but slower hardware would cross it. The cached id sets still feed a term_set_query beside the full candidate query, whose scoring over ~4.4k matches dominates. Options: cache the compiled Tantivy query per (canonical, index_version), or score verified candidates from the cached ids only. (Replaces the archived task-075 finding, whose 147 ms came from a noisy 20-round run.)
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 main-2-pop warm search p95 < 70 ms in report_80k.py (200 warm rounds) on a quiet machine
- [ ] #2 Differential suite green; scores unchanged (determinism test)
<!-- AC:END -->
