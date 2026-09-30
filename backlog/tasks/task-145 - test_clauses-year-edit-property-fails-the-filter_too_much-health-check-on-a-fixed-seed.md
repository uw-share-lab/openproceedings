---
id: TASK-145
title: >-
  test_clauses year-edit property fails the filter_too_much health check on a
  fixed seed
status: To Do
assignee:
  - '@jeevanp03'
created_date: '2026-09-30 06:40'
updated_date: '2026-09-30 06:44'
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
- [ ] #1 The test's strategy builds inputs that meet its preconditions (a query that parses with a toggleable year clause, and at most MAX_YEAR_RANGES ranges) instead of rejecting draws with assume(); `--hypothesis-show-statistics` under the `pr` profile shows under 20% of draws rejected for this test
- [ ] #2 A regression check runs the property at seed 197275319351247031457750150800712837025 (e.g. a `@seed` variant or a seeded pytest run in the suite) and it passes, as do runs under `--hypothesis-profile=pr` and `ci`; the before/after rejected-draw shares are recorded in the task notes
- [ ] #3 The property still covers what it covered before: native and scholar modes, near-cap queries, and year clauses that are and aren't already present (checked, e.g., with `hypothesis.event` counts, and noted before and after)
- [ ] #4 No health check is suppressed to make it pass
<!-- AC:END -->
