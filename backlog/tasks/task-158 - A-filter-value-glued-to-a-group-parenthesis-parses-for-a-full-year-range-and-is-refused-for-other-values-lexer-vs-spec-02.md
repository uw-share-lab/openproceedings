---
id: TASK-158
title: >-
  A full year range glued to a group parenthesis parses while every other glued
  filter value is refused (lexer vs spec 02)
status: In Progress
assignee: []
created_date: '2026-10-02 00:40'
updated_date: '2026-10-02 04:15'
labels:
  - query
milestone: m-3
dependencies: []
references:
  - backend/src/openproceedings/query/lexer.py
  - docs/specs/02-query-language.md
  - .claude/skills/query-grammar/SKILL.md
  - .claude/skills/codemirror-lezer/SKILL.md
ordinal: 133000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Source: a deferral in TASK-153's query-semantics review (PR #61 body, Review, Deferral). Spec 02 §Grammar and the lexer's docstring say a `(` glued to a preceding word or phrase, or a `)` to a following one, is `PARSE_PAREN_TOUCHES_WORD` (`model(s)`, `"a"(b)`), because a glued parenthesis would otherwise silently split a query. Spec 02 exempts no filter value, and its §Filter clauses caps paragraph relies on the rule: a bare `track:workshop(x OR y)` "would be `PARSE_PAREN_TOUCHES_WORD`". On origin/dev 122e368, a `(` glued after a filter value is refused for every value but a full year range: `year:2021(x)`, `venue:iclr(x)`, `track:main(x)` and `title:y(x)` give `PARSE_PAREN_TOUCHES_WORD`, while `year:2020..2022(x)` parses as `x AND year:2020..2022`. On the `)` side the split is whether a field prefix follows: `(x)y` and `(x)"a"` are refused, but `(x)year:2020..2022`, `(x)year:2021`, `(x)venue:iclr`, `(x)title:y` and `(x)track:main` all parse. The open-range forms (`year:..2022(x)`, `year:2020..(x)`, `(x)year:..2022`) say nothing about this rule: `..2022` and `2020..` are invalid `year:` values on their own (spec 02 §Fields and filters lists only `2024` and `2020..2026`), so bare `year:2020..` and `year:..2022` are `FIELD_UNKNOWN_VALUE`. But bare `year:..2022` also raises a `WARN_SYMBOLS_DROPPED` that reads `..2022` as a search word ("matches every `2022`"), which is wrong for a filter value that is refused anyway.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A decision, recorded with its reason in spec 02 §Grammar, §Filter clauses (the caps paragraph's `track:workshop(x OR y)` example) and the query-grammar skill: either a filter clause glued to a parenthesis is refused like a glued word (and whether that covers a `)` before a field prefix), or spec 02 lists exactly which glued forms are accepted and why
- [x] #2 A parametrized parse test pins the outcome (parse, or each error code and span) of `year:2020..2022(x)`, `year:2021(x)`, `venue:iclr(x)`, `track:main(x)`, `title:y(x)`, `(x)year:2020..2022`, `(x)year:2021`, `(x)venue:iclr`, `(x)title:y` and `(x)track:main`, and every outcome matches the decision
- [x] #3 A glued form whose year value is invalid (`year:..2022(x)`, `year:2020..(x)`, `(x)year:..2022`) reports `FIELD_UNKNOWN_VALUE` on the value, plus `PARSE_PAREN_TOUCHES_WORD` where the decision refuses that glued form; a test pins each
- [x] #4 Bare `year:..2022` reports `FIELD_UNKNOWN_VALUE` without a `WARN_SYMBOLS_DROPPED` that reads the value as a search word (a test pins it, and one that `..2022` as a text term still warns)
- [x] #5 If a query that parses today becomes refused, a decision record says whether `QUERY_VERSION` is bumped (decision-003; decision-008 is the precedent; query-grammar skill §Idempotence), and the editor lexer tables and golden generated from lexer.py are regenerated (codemirror-lezer skill) with the frontend editor tests passing
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Refuse a ( glued to any filter value (RANGE joins WORD/PHRASE); keep ) before a field prefix accepted (facet splices write field:(…) after a ) on real Trust-Evals strings); let a filter value's own check report under a glue error; skip text warnings for filter values; decision-027 (QUERY_VERSION stays 2); spec 02, lexer docstring, query-grammar skill; regenerate lexer golden.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Decision-027 (decision-026 is taken by TASK-155's branch). First tried refusing a ) glued to a field prefix too: test_clauses failed on the Trust-Evals strings (…)(source:ICLR OR …) → the venue splice writes …)venue:(ICLR)) and on year:(2019)status:accepted, so that side stays accepted. Newly refused: a typed full range glued to ( (year:2020..2022(x)). No canonical string writes a value before ( (clauses joined by ' AND '), so stored canonical and identification_query strings re-parse unchanged and QUERY_VERSION stays 2. Verified: test_lexer, test_parser (new GLUED_CLAUSES table, both modes), test_clauses, test_properties, the lexer golden (regenerated) and frontend src/editor + src/builder vitest (2,274 passed).
<!-- SECTION:NOTES:END -->
