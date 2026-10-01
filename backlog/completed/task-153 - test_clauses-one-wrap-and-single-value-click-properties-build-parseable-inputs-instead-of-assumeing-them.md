---
id: TASK-153
title: >-
  test_clauses one-wrap and single-value-click properties build parseable inputs
  instead of assume()ing them
status: Done
assignee:
  - '@jeevanp03'
created_date: '2026-09-30 20:06'
updated_date: '2026-10-01 12:41'
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
- [x] #1 For each of the two properties, the share of draws rejected (`assume` plus Hypothesis overruns, from `--hypothesis-show-statistics` under the `pr` profile) is measured on dev before the change and recorded in the notes
- [x] #2 Each property either draws from a strategy that builds only parseable inputs, with its `assume()` replaced by an asserted precondition and under 20% of draws rejected under the `pr` profile (as TASK-145 measures), or keeps its `assume()` with the reason written in the property-testing skill (e.g. the broad strategy is shared with properties that need unparseable inputs, and a rebuilt one would cost more than it saves)
- [x] #3 Where a strategy is rebuilt, near misses (inputs that do not parse) are still generated and asserted to be refused for the right reason, so the property can still see a wrongly accepted input
- [x] #4 No health check is suppressed for either property, and both pass at the `ci` profile
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Baseline on dev (49fd6e0), pr profile, --hypothesis-show-statistics, 3 runs each:
- one-wrap (max_examples=60): 41/101, 55/115, 44/104 invalid; all assume() (gave up 29.7%, 27.8%, 26.9%).
- single-value-click (200): 293/493, 365/565, 316/516 invalid (59%, 65%, 61%); assume() gave up 31.2%, 32.4%, 30.4% of all draws, the rest Hypothesis overruns.

Finding: the rebuilt wrap_cases reached a window the old strategy rarely drew (short words, ~1,800-1,870 code points, e.g. 'trust' x 300): the combined wrap is too long but every field's own fits, so filter_clauses parses 5 times (as spec 02 says) while every field is toggleable. The old cost bound read 'every field toggleable' as 'written together' and failed there (confirmed: the dev version of the property fails with this input as an @example, 'assert 5 <= (0 + 1)'). Test bug, not a code bug: the bound now asks clauses._check_wrap for the combined wrap; the input is pinned.

Mutation check (temporary edits to backend/src, restored), pr profile, the two properties with and without their @examples: all 5 mutants killed by generated cases alone. M1 _check_wraps treats a too-long combined wrap as every field's answer (one-wrap); M2 parser drops the all-negative check (click near misses); M3 _check_splice never checks the widest edit (click); M4 _check_wraps never checks (one-wrap); M5 a nested-only field reported with no reason (one-wrap).

After, on 6352e07 (pr derandomized): one-wrap 8/68 invalid, click 18/218, all overruns, no 'gave up' line (earlier random pr runs: one-wrap 6-16% over 8 runs, click 5-12% over 5). ci: test_clauses.py 144 passed (click 182/2166 invalid, one-wrap 8/62). No health check suppressed; the one-wrap keeps its deadline=None with the reason comment from decision-024; the click property uses the profile deadline. make test: 5976 passed, 2 skipped; frontend 3052 passed. make lint, make tooling green.

Overrun measurements (TASK-153 learning): real property, random pr runs: click_cases first version 72/272, 43/243, 61/261 invalid (18-27%), after own-label decisions 5-12% (5 runs). Trivial-body harness (scratchpad, 5x200 per variant): click ~26% -> ~10%; queries() ~13% -> 6%. Attribution harness: 201 overruns from mutation vs 8 from generation over 4x200 click cases; by copied label, ONE_FROM_MANY (st.lists elements) 114 of about 200. Coverage events, click property: toggleable venue/track/status about 50-60% of cases vs 60-83% on dev (scratch copy with events), non-toggleable verdicts about 45% vs 25%. Review: depth padding drawn 58..66 so the PARSE_TOO_DEEP near miss is generated; near-miss assert is exact (codes == {refused}); one-wrap asserts the spec's at most five parses and pins a too-deep wrap.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
The one-wrap and single-value-click properties draw from wrap_cases() and click_cases() (backend/tests/strategies.py), which build parseable queries plus near misses that parse must refuse with their code; assume() is gone (27-32% rejected before, none now; invalid draws 5-16%, all mutator overruns, cut further by giving size-changing decisions their own sampled_from labels). The rebuild found a wrong cost bound in the one-wrap property (test bug, pinned as an @example). clause_queries removed. Property-testing skill and a learning entry updated.
<!-- SECTION:FINAL_SUMMARY:END -->
