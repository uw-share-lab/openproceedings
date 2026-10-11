---
id: TASK-220
title: >-
  Re-run the group-count benchmark on the 166,757-record index on a quiet
  machine
status: Done
assignee: []
created_date: '2026-10-10 03:47'
updated_date: '2026-10-11 00:15'
labels:
  - perf
  - new-venues
dependencies: []
ordinal: 153000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
docs/results/2026-10-10-bench-group-counts.md (index 757641db0a20) ended at load 5.3, above the report's 5 limit, so it is not citable. Re-run tests.bench.group_counts_report on a copy of the served index with load < 5 at start and end, and cite it in spec 03 if it is within budget (worst p95 was 85.2 ms).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A citable report on the current index; spec 03 cites it
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
The citable report is docs/results/2026-10-10-bench-group-counts.md on index 9977ed00669f (173,253 records, schema 4), re-run after the group-count aggregation fix 566cafcd at a 1-minute load of 3.3 at the start and 3.7 at the end (under 5). Worst first-page p95 with group counts is 76.5 ms (main-2-pop), within spec 03 100 ms budget; spec 03 Performance budgets cites it. It supersedes the report on 757641db0a20, which ended at load 5.3. The synthetic 80k report (2026-10-11-bench.md) finds main-3-sources at 110.7 ms, over budget; that is filed as its own follow-up.
<!-- SECTION:FINAL_SUMMARY:END -->
