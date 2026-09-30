---
id: TASK-153
title: >-
  test_clauses one-wrap and single-value-click properties build parseable inputs
  instead of assume()ing them
status: To Do
assignee:
  - '@jeevanp03'
created_date: '2026-09-30 20:06'
updated_date: '2026-09-30 20:10'
labels:
  - tests
milestone: m-3
dependencies:
  - TASK-145
references:
  - backend/tests/unit/test_clauses.py
  - backend/tests/strategies.py
  - .claude/skills/property-testing/SKILL.md
priority: low
ordinal: 129000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Source: a TASK-145 (PR #56) deferral. TASK-145 rebuilt `test_every_year_edit_on_a_toggleable_clause_parses_and_edits_only_that_clause` in `backend/tests/unit/test_clauses.py`: it used to draw a `clause_queries()` or `near_cap_queries(1_800, 2_000)` string and `assume()` that it parsed with a toggleable year clause, which threw away 66-79% of draws and failed Hypothesis's `filter_too_much` health check at a fixed seed. Two other properties in the same file still `assume()` a successful parse: `test_the_one_wrap_parse_answers_exactly_as_per_field_parses` (`assume(result.ast is not None)` over `queries()` and `near_cap_queries(1_800, 2_000)`) and `test_every_single_value_click_on_a_toggleable_clause_parses_and_edits_only_that_clause` (`assume(before.ast is not None)` over `clause_queries()`). They pass the health checks today, so PR #56 left them and recorded that choice in its learning, but they discard draws the same way, so they test fewer inputs than their example counts suggest and can start failing `filter_too_much` when a strategy changes. PR #56's learning also says that a strategy that builds only valid inputs should build near misses too, and assert the code refuses them for the right reason. Depends on TASK-145 for the `year_edit_cases` pattern and the property-testing skill text it adds.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 For each of the two properties, the share of draws rejected (`assume` plus Hypothesis overruns, from `--hypothesis-show-statistics` under the `pr` profile) is measured on dev before the change and recorded in the notes
- [ ] #2 Each property either draws from a strategy that builds only parseable inputs, with its `assume()` replaced by an asserted precondition and under 20% of draws rejected under the `pr` profile (as TASK-145 measures), or keeps its `assume()` with the reason written in the property-testing skill (e.g. the broad strategy is shared with properties that need unparseable inputs, and a rebuilt one would cost more than it saves)
- [ ] #3 Where a strategy is rebuilt, near misses (inputs that do not parse) are still generated and asserted to be refused for the right reason, so the property can still see a wrongly accepted input
- [ ] #4 No health check is suppressed for either property, and both pass at the `ci` profile
<!-- AC:END -->
