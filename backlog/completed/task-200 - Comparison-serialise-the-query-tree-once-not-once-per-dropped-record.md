---
id: TASK-200
title: 'Comparison: serialise the query tree once, not once per dropped record'
status: Done
assignee: []
created_date: '2026-10-06 04:08'
updated_date: '2026-10-06 18:55'
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
- [x] #1 The tree is serialised once per comparison, with a test that the dropped-record path calls model_dump_json a bounded number of times
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Test: count _Node.model_dump_json over a comparison of 2 and 12 rows on each evidence path (query_limit, stemming, compat_reading, scholar_missed): equal. 2. ids() keeps a by-identity cache (node held beside its matches) in front of the serialised memo. 3. Trees built per row (deciding's form terms, fields' per-field leaf copies) are built once per comparison.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Before the fix the counts grew with the rows on all four evidence paths, not only ids(unlimited): query_limit 16->26, stemming 20->50 (deciding built a Term per form per row), compat_reading 20->60 (rewrites), scholar_missed 30->110 (fields copied each leaf per row). All four are now flat. Validation: test_scholar_compare.py 143 passed; test_scholar_report.py + contract test_compare.py 242 passed; ruff and mypy --strict backend/src clean.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
compare_query's ids() now caches by tree identity in front of its serialised memo, and the trees a row's evidence asks about (each inflected form's term, each leaf in each text field) are built once per comparison, so no row serialises a tree: the count is the same for 2 rows as for 12 on the query_limit, stemming, compat_reading and scholar_missed paths (test_a_rows_evidence_serialises_no_tree_per_row). Results unchanged: the scholar_compare, scholar_report and contract compare suites pass.
<!-- SECTION:FINAL_SUMMARY:END -->
