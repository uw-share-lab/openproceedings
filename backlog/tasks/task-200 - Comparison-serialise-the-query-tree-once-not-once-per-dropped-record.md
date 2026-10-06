---
id: TASK-200
title: 'Comparison: serialise the query tree once, not once per dropped record'
status: To Do
assignee: []
created_date: '2026-10-06 04:08'
updated_date: '2026-10-06 04:22'
labels:
  - compare
  - perf
milestone: m-4
dependencies: []
ordinal: 143000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The v0.2.0 release security review (2026-10-06) found eval/scholar_compare.py:1097 calls ids(unlimited), which serialises the tree with model_dump_json() once per dropped record before it reaches the memo. The cost is bounded (5,000 records, the comparison's time cap and its ticks), so it is no vulnerability, but hoisting the serialisation out of the loop removes repeated work.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The tree is serialised once per comparison, with a test that the dropped-record path calls model_dump_json a bounded number of times
<!-- AC:END -->
