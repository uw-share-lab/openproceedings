---
id: TASK-185
title: >-
  Comparison: a file's paper outside the query's own year or venue limit needs
  its own class
status: Done
assignee: []
created_date: '2026-10-05 08:39'
updated_date: '2026-10-06 00:10'
labels:
  - eval
  - api
milestone: m-3
dependencies: []
ordinal: 129000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-177 found that eval/scholar_compare.py classes a file record that the query's own year: or venue: clause excludes as full_text, which tells the reviewer the text did not match when the filter did the excluding.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Such a record is reported with a class and reason naming the query's own limit, in op eval scholar and POST /compare, with tests; spec 07 and the protocol skill state it
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. scholar_compare: QUERY_LIMIT class after our_bug; query_limits() = the query's own top-level non-default filter clauses; dropped rows failing one -> query_limit with clause, failing value and whether the rest matches; not_found rows judged on the file's venue/year (unsettled). 2. scholar_report meaning/method/human classes. 3. API CompareReason + make openapi; frontend labels; compare fixture gains a limited answer. 4. spec 07/04/05, protocol skill. 5. Tests.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Generalised slightly beyond year:/venue:: any top-level filter clause the query writes that is not the default (a user's own track:/status: too) is a limit, since such a record was also misfiled as full_text. Unmatched (not_found) records are judged on the file's own venue and year and stay unsettled for a person. test_openapi_additive.py could not see inside a nullable enum (anyOf [enum, null]) and called any new value 'changed'; it now judges each anyOf option by the same rules (with cases), so a new value in a nullable open enum is additive. Pre-existing, unrelated: test_compare.py::test_the_added_papers_come_as_the_exports_own_ris fails on clean HEAD after UTC midnight (the /compare RIS is pinned to DATE, /export uses today).

Validation: test_scholar_compare.py 77 passed; test_scholar_report.py 61 passed; contract -k 'compare or scholar or openapi or schema' 702 passed + 2 failed (the pre-existing date-dependent added_papers test, and test_openapi_additive before its anyOf fix; it now passes 20/20); npm test --workspace frontend -- compare 41 passed.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
A file record that a top-level filter clause the query itself writes (year:, venue:/source:, their NOT, or a non-default track:/status:) excludes is now class query_limit, tested right after our_bug, with evidence naming the clause, the failing value and whether the rest of the query matches (plus 'also fails the filters'). Unmatched not_found records are judged on the file's venue and year and go to a person. Same rows in op eval scholar (report meaning, Method bullet, human_class) and POST /compare (CompareReason gains query_limit; openapi.json and schema.ts regenerated; frontend labels and next step; compare-fixture.json gains a 'limited' answer). Spec 07/04/05, the protocol and api-contract skills updated. test_openapi_additive now judges nullable enums inside anyOf.
<!-- SECTION:FINAL_SUMMARY:END -->
