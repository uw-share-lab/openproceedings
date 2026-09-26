---
id: TASK-014
title: 'Default filters, WARN_NESTED_FILTER and identification_query'
status: In Progress
assignee:
  - '@jeevan'
created_date: '2026-09-26 01:06'
updated_date: '2026-09-26 02:51'
labels:
  - query
milestone: m-1
dependencies:
  - TASK-013
ordinal: 13000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Spec 02 §Default filters: content-based recognition, top-level-only suppression, identification string.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 trust, its canonical string, and a replay of it give identical excluded (golden round-trip cases incl. toggle off/on)
- [x] #2 Nested track:/status: under OR keeps the default and raises WARN_NESTED_FILTER
- [x] #3 identification_query = canonical minus default conjuncts, returned in ParseResult
<!-- AC:END -->
