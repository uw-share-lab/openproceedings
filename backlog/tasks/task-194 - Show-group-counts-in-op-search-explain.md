---
id: TASK-194
title: Show group counts in op search --explain
status: To Do
assignee: []
created_date: '2026-10-05 08:39'
labels:
  - cli
milestone: m-3
dependencies: []
ordinal: 138000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-176's counts are in /search only; the CLI's --explain shows the parse and compiled query but not which group narrows the result.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 op search --explain prints each group's total and total_without under the same bounds, or the not_counted reason
<!-- AC:END -->
