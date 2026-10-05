---
id: TASK-196
title: >-
  Group counts push a cold first page of a wildcard-phrase query over the 100 ms
  p95 budget
status: Done
assignee: []
created_date: '2026-10-05 13:59'
updated_date: '2026-10-05 17:21'
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
- [x] #1 The cold first page of every Trust-Evals string with default group counts is under the 100 ms p95 budget on the current index, measured as in the bench doc; or the budget's treatment of the cold group-count case is decided and recorded with the measurement
- [x] #2 Re-measured with group_counts_report.py at a sustained 1-minute load under 5 (the load at the start and the end both under 5, as the bench doc records it), and spec 03's 'Exception, as measured (TASK-196)' bullet and spec 04's Cost figures updated from that run or removed
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-05 (gate round 2, PERF-R2-1/DOC-R2-S3): spec 03 §Performance budgets now carries 'Exception, as measured (TASK-196)' for this miss; spec 04 §SearchResponse Cost and docs/results/2026-10-05-bench-group-counts.md cite this task. The bench's timed /search rows now assert that no measured round skipped its counting (PERF-R2-N c).

PR #105 CI (2026-10-05): the advisory bench job's 20% gate failed on test_search_endpoint_first_page because the head's bench now asks for group counts and the base's never did (PERF-S1): fixture minima rose 108–1031% (main-7-most-updated 6.6 → 16.4 ms; llm-as-judge 0.54 → 6.1 ms), all under the 100 ms budget. Once this PR is on dev the baseline includes counts; this task decides whether the cold first page needs work.

2026-10-05 re-measure (group_counts_report.py, load 3.9 → 3.3, commit bed0a6cb plus a Trust-Evals table added to the report): the wildcard-phrase query's cold first page with counts is p95 84.4 ms, within the budget; its 110.8 ms was a load effect. The report now times every Trust-Evals string, and main-2-pop is over the budget: p95 190.1 ms with counts, 62.1 ms without. Profiled on a scratch index copy: its first group (~35 ms a run) is collected again in three of six counted trees; aggregation vs Tantivy's count collector make no difference (sums equal on all 58 trees); reusing the group's matches as an ord term set halves those trees but leaves the page near 120 ms. Filed TASK-197 for the fix.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Re-measured at a 1-minute load under 5 with every Trust-Evals string added to the bench report. The query this task named is within the 100 ms budget (p95 84.4 ms); main-2-pop is the one cold first page over it (p95 190.1 ms with counts). decision-039 keeps the budget and records that case as spec 03's exception 'as measured'; spec 03 and spec 04's Cost figures are updated from the run; TASK-197 holds the cause, the measured partial fix and the work to bring it under.
<!-- SECTION:FINAL_SUMMARY:END -->
