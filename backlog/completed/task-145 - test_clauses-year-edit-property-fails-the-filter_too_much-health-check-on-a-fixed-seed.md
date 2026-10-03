---
id: TASK-145
title: >-
  test_clauses year-edit property fails the filter_too_much health check on a
  fixed seed
status: Done
assignee:
  - '@jeevanp03'
created_date: '2026-09-30 06:40'
updated_date: '2026-09-30 16:53'
labels:
  - tests
  - bug
milestone: m-3
dependencies: []
references:
  - backend/tests/unit/test_clauses.py
  - backend/tests/strategies.py
ordinal: 122000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found while rebasing TASK-142 (PR #47, 2026-09-30); it reproduces on plain dev. `backend/tests/unit/test_clauses.py::test_every_year_edit_on_a_toggleable_clause_parses_and_edits_only_that_clause` (its `@given` is at test_clauses.py:462; the traceback points at 463) fails deterministically with `--hypothesis-seed=197275319351247031457750150800712837025`: Hypothesis raises FailedHealthCheck (filter_too_much), with about 8-9 inputs generated successfully against 50 filtered out (the exact count varies by run). The test draws any `clause_queries()` or `near_cap_queries(1_800, 2_000)` string and then `assume()`s that it parses, that its year clause is toggleable with a span, and that the drawn ranges fit MAX_YEAR_RANGES, so on an unlucky seed most draws are thrown away. A health-check failure fails the required `test` job for a change that did not touch clauses.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The test's strategy builds inputs that meet its preconditions (a query that parses with a toggleable year clause, and at most MAX_YEAR_RANGES ranges) instead of rejecting draws with assume(); `--hypothesis-show-statistics` under the `pr` profile shows under 20% of draws rejected for this test
- [x] #2 A regression check runs the property at seed 197275319351247031457750150800712837025 (e.g. a `@seed` variant or a seeded pytest run in the suite) and it passes, as do runs under `--hypothesis-profile=pr` and `ci`; the before/after rejected-draw shares are recorded in the task notes
- [x] #3 The property still covers what it covered before: native and scholar modes, near-cap queries, and year clauses that are and aren't already present (checked, e.g., with `hypothesis.event` counts, and noted before and after)
- [x] #4 No health check is suppressed to make it pass
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Measure the baseline: rejected-draw share under --hypothesis-show-statistics (pr), the seeded failure, and event counts (mode, source, year present/absent).
2. Add year_edit_cases() to backend/tests/strategies.py: clause_queries shapes and near-cap parts with the toggleability rules in the grammar (no year filter but the one top-level clause, a positive part in every OR branch, OR groups parenthesised inside AND, parts glued only where ) meets ( ); pads toward the length and depth caps cut back by one parse of the widest year edit.
3. Keep the property's coverage of false positives: about one case in five is a near miss built one step past a rule (negated, two clauses, nested, mixed fields, one pad step too long or too deep), which filter_clauses must refuse with that reason; one of each pinned with @example.
4. Rewrite the property over year_edit_cases with asserts in place of assume(), hypothesis.event counts, ranges cut to MAX_YEAR_RANGES; add a @seed regression variant at the failing seed.
5. Measure after (pr x10, seed, ci), mutation-check on a scratch copy, run make test, lint, tooling.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Before (dev d76a38b, pr profile, --hypothesis-show-statistics): seed 197275319351247031457750150800712837025 fails FailedHealthCheck filter_too_much (9 valid, 50 filtered). Unseeded runs: 595/795, 769/969, 613/813, 586/786 invalid (72-79%); 41-44% of cases gave up at assume(parse), 18-22% at assume(toggleable). Events on a scratch copy of the old test (3 runs): of all cases, year present 2-7%, absent 18-26%, native 11-17%, scholar 9-17%, near-cap (len >= 1,700) 0% of passing cases: the near-cap branch almost never produced a valid input (its canonical form over the cap, or a year filter nested under OR).

After (year_edit_cases, pr profile): 0 cases rejected by the test (no 'gave up because' line). Invalid counts are all Hypothesis overruns ('exceeded maximum test case size', checked with HYPOTHESIS_EXPERIMENTAL_OBSERVABILITY): 20 runs on the committed code gave 27-46 invalid per 200 valid (10-19%) in 19 runs and 58/258 (22.5%) in one. Seeded variant at the old seed (pr): 200 passing, 43 invalid (17.7%). ci profile: 2,000 passing, 335 invalid (14%); seeded variant 200 passing. Events (pr, typical run): native 42-48%, scholar 39-47%, near-cap 35-59%, clause 23-40%, clause padded toward the length cap 3-14%, toward the depth cap 0-8%, year present (spliced) 34-52%, absent (wrapped) 31-50%, edit within 200 code points of the cap 27-65%; near misses (refused with the reason built) too_long 3-9%, negated/multiple_clauses/nested/mixed_fields 0-6% each, and one of each reason pinned with @example.

A ci run found a strategy bug (63 parens around NOT NOT year:2021: the query too deep while its widest edit was not); the property's assert caught it and the fit now parses the query as well as the edit.

Mutation check on a scratch copy of query/clauses.py: too_long never reported below 2,100 code points: killed; a negated year clause reported toggleable: killed (the old property could not see this one); a year filter nested under OR not reported: killed; the multiple_clauses count check removed: survives, equivalent (the splice check reports multiple_clauses anyway).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
The year-edit property now draws from year_edit_cases() (backend/tests/strategies.py), which builds queries whose year clause is toggleable instead of drawing any clause or near-cap query and assume()ing it: the toggleability rules are in the grammar, and padding toward the length and depth caps is cut back by parsing the query and its widest year edit. The test asserts the preconditions instead of assuming them. About one case in five is a near miss built one step past a rule, which filter_clauses must refuse with that reason, so the property still catches a clause wrongly reported toggleable (one of each reason pinned with @example). A @seed variant runs it at the seed that failed filter_too_much. Rejected by the test: 72-79% before, 0 after; total invalid shown by --hypothesis-show-statistics (all Hypothesis overruns) 10-19% in 19 of 20 pr runs, 22.5% in one; ci 14%. Near-cap edits went from none to about half the cases, a year clause to splice from 2-7% to 34-52%. Verified: pr x20, seeded, ci runs; mutation checks on a scratch copy; make test, make lint, make tooling. Test-only: no backend/src change, no health check suppressed.
<!-- SECTION:FINAL_SUMMARY:END -->
