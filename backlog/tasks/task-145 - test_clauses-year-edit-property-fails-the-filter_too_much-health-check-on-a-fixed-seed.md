---
id: TASK-145
title: >-
  test_clauses year-edit property fails the filter_too_much health check on a
  fixed seed
status: To Do
assignee:
  - '@jeevanp03'
created_date: '2026-09-30 06:40'
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
Found while rebasing TASK-142 (PR #47, 2026-09-30); it reproduces on plain dev. `backend/tests/unit/test_clauses.py::test_every_year_edit_on_a_toggleable_clause_parses_and_edits_only_that_clause` (the `@given` at test_clauses.py:463) fails deterministically with `--hypothesis-seed=197275319351247031457750150800712837025`: Hypothesis raises FailedHealthCheck (filter_too_much), "8 inputs were generated successfully, while 50 inputs were filtered out". The test draws any `clause_queries()` or `near_cap_queries(1_800, 2_000)` string and then `assume()`s that it parses, that its year clause is toggleable with a span, and that the drawn ranges fit MAX_YEAR_RANGES, so on an unlucky seed most draws are thrown away. A health-check failure fails the required `test` job for a change that did not touch clauses.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The test's strategy builds inputs that meet its preconditions (a query that parses with a toggleable year clause, and at most MAX_YEAR_RANGES ranges) instead of rejecting most draws with assume(); any assume() left rejects only a small fraction
- [ ] #2 The failing seed is pinned as a regression check (an `@example` for the input it drew, or a seeded run in the test suite), and the test passes at that seed and under the `pr` and `ci` profiles
- [ ] #3 The property still covers what it covered before: native and scholar modes, near-cap queries, and year clauses that are and aren't already present (checked, e.g., with `hypothesis.event` or `target` counts, or a note of the draw mix before and after)
- [ ] #4 No health check is suppressed to make it pass
<!-- AC:END -->
