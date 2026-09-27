---
id: TASK-076
title: Headroom for warm searches over wildcard phrases at 80k
status: To Do
assignee: []
created_date: '2026-09-26 23:03'
updated_date: '2026-09-27 01:04'
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
- [ ] #1 Differential suite green; scores unchanged (determinism test)
- [ ] #2 main-2-pop warm search p95 < 50 ms and p99 < 100 ms over 200 warm rounds in report_80k.py on a quiet machine
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Numbers: the committed report (200 warm rounds) gives 68.7 ms p95; a separate 200-run probe (not in docs/results) gave p95 95 ms, p99 148 ms.

From the M2 gate: TantivyEngine.compile is now memoised per tree (bounded), so a search's pages and facets don't rebuild the Boolean; the balanced combine trees cost ~5x Python compile time for wide wildcards (perf review). Re-measure main-2-pop warm with report_80k.py before other work.

M2 gate: with the compiled-query memo, docs/results/2026-09-27-bench.md (200 warm rounds, quiet, 2700e19) gives main-2-pop warm p95 27.3 ms (was 68.7). AC#1's p95 < 50 ms is met in that report; its p99 < 100 ms isn't measured by the report yet (add a p99 column, or a probe) before closing.

Correction: after the AC reorder, the p95/p99 criterion is AC#2 (AC#1 is the differential suite); AC#2's p95 < 50 ms is met in the report, its p99 not yet measured.

Report regenerated at f0de68b (clean, quiet): main-2-pop warm p95 27.5 ms, cold search 10.1 s, match_ids + exclusions 10.5 s. Supersedes the 2700e19 figures above.
<!-- SECTION:NOTES:END -->
