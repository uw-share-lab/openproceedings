---
id: TASK-014
title: 'Default filters, WARN_NESTED_FILTER and identification_query'
status: Done
assignee:
  - '@jeevan'
created_date: '2026-09-26 01:06'
updated_date: '2026-09-26 03:33'
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

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
query/defaults.py: defaults added on the canonical tree; recognised by content as the sole top-level clause; NOT track:x suppresses; WARN_NESTED_FILTER on every path; identification_query and identification_ast; ParseResult.effective_ast/defaults for exclusion accounting (task-026).
<!-- SECTION:FINAL_SUMMARY:END -->
