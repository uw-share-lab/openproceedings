---
id: TASK-220
title: >-
  Re-run the group-count benchmark on the 166,757-record index on a quiet
  machine
status: To Do
assignee: []
created_date: '2026-10-10 03:47'
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
- [ ] #1 A citable report on the current index; spec 03 cites it
<!-- AC:END -->
