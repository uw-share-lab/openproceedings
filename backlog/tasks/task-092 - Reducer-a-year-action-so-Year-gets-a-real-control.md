---
id: TASK-092
title: 'Reducer: a year action so Year gets a real control'
status: Done
assignee: []
created_date: '2026-09-27 20:29'
updated_date: '2026-09-27 20:55'
labels:
  - frontend
milestone: m-3
dependencies: []
ordinal: 89000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
From TASK-033 design: search-state.ts has no year toggle/range action; add one (writes year:(a..b) grouped per decision-011/TASK-078 rules), with goldens shared with the backend.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 search-state.ts has year actions (set, clear, add a range, remove a range) that write a grouped year clause from the /parse year report, refusing (and whyBlocked reporting) as the other fields do
- [x] #2 The /parse year toggleable check covers every edit the actions can write
- [x] #3 Golden cases shared with the backend prove every edit parses and only the year clause changes
- [x] #4 Specs 02 and 05, decision-011 and the design doc describe the year action
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Reducer year actions in search-state.ts (yearSet, yearClear, yearAdd, yearRemove) built from the /parse year report via yearClauseFromParse, writing a grouped year clause merged as the canonical form merges; the same refusals and whyBlocked as the other fields, plus NOT_INCLUDED and TOO_MANY_RANGES. 2. Bound a year clause to MAX_YEAR_RANGES ranges and make the widest year edit in query/clauses.py that many full-width ranges, so the toggleable check covers every year edit (the revisit decision-011 names). 3. A shared golden, frontend/src/lib/year-clause-golden.json, read by the reducer test, test_clauses.py and the /parse contract test: the backend parses every expected edit, its year clause admits exactly the expected ranges, and nothing else changes. 4. Specs 02 and 05, decision-011 and the search-workspace design updated.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Actions yearSet, yearClear, yearAdd, yearRemove (YearAction) with yearClauseFromParse, formatYearClause, MIN_YEAR/MAX_YEAR/MAX_YEAR_RANGES/EVERY_YEAR. The splice/wrap code was split into checkClause + placeClause + withinLength so year and value fields share the same STALE/WRONG_FIELD/NEGATED/BAD_SPAN/EMPTY_QUERY/TRAILING_ESCAPE/TOO_LONG paths; editable() and noEditableClause() word /parse's reasons for year too. New codes: NOT_INCLUDED (removing years not admitted), TOO_MANY_RANGES (more than 4). Clear writes year:(1000..9999) in place rather than deleting the clause (deleting could leave a dangling operator). Backend: clauses.py's widest year edit is now MAX_YEAR_RANGES=4 disjoint full-width ranges (59 code points instead of 17), so every edit the reducer can write is covered by the toggleable check; existing goldens unchanged. Shared golden frontend/src/lib/year-clause-golden.json (33 cases, every action and every /parse reason, both cap edges) read by search-state.test.ts, test_clauses.py (report, edit parses, year ranges_after, other conjuncts and other fields' reports unchanged, constants tie) and test_parse_filters.py; plus a hypothesis property test of arbitrary up-to-4-range edits on generated and near-cap queries. The year control UI itself is not built (design keeps the read-only list; Open questions 2 updated).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Added reducer year actions (yearSet, yearClear, yearAdd, yearRemove) and yearClauseFromParse to search-state.ts. They write a grouped, merged year clause over the /parse year clause and use the same refusal and whyBlocked paths as the other fields, plus two new codes, NOT_INCLUDED and TOO_MANY_RANGES (more than 4). query/clauses.py now checks the widest year edit as MAX_YEAR_RANGES=4 disjoint full-width ranges, so /parse's toggleable answer covers every year edit (recorded in decision-011). The new shared golden year-clause-golden.json (33 cases) is read by the reducer test, test_clauses.py and test_parse_filters.py. A hypothesis property test covers arbitrary 4-range edits. Specs 02 and 05 and the design doc are updated. Verified: uv run pytest 3835 passed, npm test 348 passed, make lint, make tooling.
<!-- SECTION:FINAL_SUMMARY:END -->
