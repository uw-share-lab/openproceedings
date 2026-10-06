---
id: TASK-194
title: Show group counts in op search --explain
status: Done
assignee: []
created_date: '2026-10-05 08:39'
updated_date: '2026-10-06 00:06'
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
- [x] #1 op search --explain prints each group's total and total_without under the same bounds, or the not_counted reason
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
op search --explain now runs search.run with limit=0 and groups at ApiConfig's defaults (max_counted_groups/terms/ids, group_count_wait/grace_seconds), so it counts what /search counts; prints 'concept groups: N, counted (at most L); total T' then one line per group '[s, e] <text>: total A, total_without W', or 'concept groups: N, not counted: <reason> (<meaning>)'. No --json form exists for --explain, so none added. Its search_run line's total now comes from run (same count). Spec 08 §CLI, spec 04 §SearchResponse groups and the ast-compilation skill updated; --explain help text too.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
op search --explain prints each concept group's total (alone) and total_without under /search's default bounds (ApiConfig), or the not_counted reason with a one-phrase meaning. Tests: test_cli_search_explain_counts_each_group (counts and the bounds passed) and test_cli_search_explain_says_why_the_groups_are_not_counted (too_many_groups) in tests/unit/engine/test_compile.py.
<!-- SECTION:FINAL_SUMMARY:END -->
