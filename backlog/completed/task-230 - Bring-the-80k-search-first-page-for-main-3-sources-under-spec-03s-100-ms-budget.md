---
id: TASK-230
title: >-
  Bring the 80k /search first page for main-3-sources under spec 03's 100 ms
  budget
status: Done
assignee: []
created_date: '2026-10-11 00:15'
updated_date: '2026-10-11 01:24'
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
- [x] #1 main-3-sources first-page p95 on the synthetic 80k corpus is under 100 ms in a report from a quiet machine (load under 5 at start and end), or spec 03 records an owner decision to accept the miss
- [x] #2 Membership and counts are unchanged (the group-count oracle and property tests pass)
- [x] #3 Spec 03 §Performance budgets and docs/README.md cite the new report
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Profile the counting job; split the counted trees across the two counting workers without changing any count; re-measure GC; regenerate both reports.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Profile (cache-tip 80k index, HEAD a3b67796): main-3-sources' counting job is 6 Tantivy collections run serially (A 19, B 7.5, C 1.8, B∧C 9.5, A∧C 21, A∧B 27 ms; ~86-93 ms) - pure query evaluation, a count costs the same as an aggregation and pushing the filters into the query doesn't help - against a 65 ms page path, so the job was the critical path (p50 108.5, p95 ~110). GC was not: with the 80k corpus resident, 1 full GC (~400 ms) in 200 rounds, under the p95.
Fix (ab2de11b): TantivyEngine.counts(spread=...) offers the trees to a helper on the other counting worker; caller and helper take trees one at a time from a shared queue (_Shared), each counted exactly as before. The caller never waits for an unstarted helper; a helper yields to another search's queued counting job (search._WAITING/_yield). Bitwise calls share conjunct bitmaps, each collected once (_Parts.matches waits for the other thread's collection); value masks built before spreading. _bitmap sets bytes via map/deque and parses base-2 digits (half the GIL-held time; main-2-pop's page path contended with it). Abandoned jobs may finish one collection per counting thread (spec 04 and the two abandonment tests updated). No gc.freeze in report or API: GC is not a p95 factor.
Tests: 7 new in test_group_counts.py (differential property test of spread vs unspread vs oracle, helper takes trees, never-starts/starts-after/yields, helper failure propagates, bitwise spread collects each conjunct once, search uses both workers, helper yields to a waiting job); full backend suite 8859 passed, 3 skipped; make lint clean.
Results: docs/results/2026-10-11-bench.md (load 4.4 start / 4.0 end, commit ab2de11b): first-page p95 7.4-74.2 ms, main-3-sources 69.9, main-2-pop 74.2, nothing over budget. docs/results/2026-10-10-bench-group-counts.md (real corpus, load 2.8/2.8, ab2de11b-dirty: dirty only by the regenerated 80k report): worst first page main-2-pop 67.7 ms (was 76.5).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
main-3-sources' first page was over budget because its six counted trees ran serially on one counting worker (~90 ms) behind a 65 ms page. A counting job now shares its trees with a helper on the other counting worker (counts unchanged: differential property test vs the oracle), and _bitmap holds the GIL half as long. Synthetic 80k first-page p95 7.4-74.2 ms (main-3-sources 69.9) in docs/results/2026-10-11-bench.md; real corpus worst 67.7 ms. Full suite 8859 passed; make lint clean.
<!-- SECTION:FINAL_SUMMARY:END -->
