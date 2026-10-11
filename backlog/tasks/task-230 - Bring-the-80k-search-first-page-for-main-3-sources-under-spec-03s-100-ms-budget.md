---
id: TASK-230
title: >-
  Bring the 80k /search first page for main-3-sources under spec 03's 100 ms
  budget
status: To Do
assignee: []
created_date: '2026-10-11 00:15'
labels:
  - perf
dependencies: []
ordinal: 159000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Milestone C's synthetic 80k benchmark (docs/results/2026-10-11-bench.md, load 2.6 to 2.8) puts the /search first page for main-3-sources at p95 110.7 ms, over spec 03's 100 ms budget; the other nine strings range from 8.4 to 96.1 ms. Without group counts the same page is 65 ms, so the excess is the group counting TASK-176 added, not index schema 4: six counted trees run one after another on one worker, each broad tree costing 15-20 ms of query evaluation. Dev already ran about 125 ms p50 here before milestone C. Schema 4's own regression (the 5-field combo in group counts, 632.8 ms before) was fixed in 566cafcd. The bisect, root cause and numbers are in the milestone's perf report, .superpowers/sdd/2026-10-10-new-venues-milestone-c/perf-report.md (a local, untracked file). It names two options, neither tried: split the counted trees across the two group workers, and keep the report process's resident 80k corpus out of the garbage collector (gc.freeze), which is a harness effect a served instance lacks. On the real corpus (index 9977ed00669f) the worst first page is 76.5 ms, so this is a synthetic-corpus miss; spec 03 §Performance budgets states it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 main-3-sources first-page p95 on the synthetic 80k corpus is under 100 ms in a report from a quiet machine (load under 5 at start and end), or spec 03 records an owner decision to accept the miss
- [ ] #2 Membership and counts are unchanged (the group-count oracle and property tests pass)
- [ ] #3 Spec 03 §Performance budgets and docs/README.md cite the new report
<!-- AC:END -->
