---
id: TASK-158
title: >-
  A filter value glued to a group parenthesis parses for a full year range and
  is refused for other values (lexer vs spec 02)
status: To Do
assignee: []
created_date: '2026-10-02 00:40'
updated_date: '2026-10-02 00:40'
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
Source: a deferral in TASK-153's query-semantics review (PR #61 body, Review, Deferral). Spec 02 §Grammar and the lexer's docstring say a `(` glued to a preceding word or phrase, or a `)` to a following one, is `PARSE_PAREN_TOUCHES_WORD` (`model(s)`, `"a"(b)`), because a glued parenthesis would otherwise silently split a query. Spec 02 exempts no filter value. On origin/dev 122e368: `year:2020..2022(x)` parses as `x AND year:2020..2022`, but `year:2021(x)`, `year:2020..(x)` and `venue:iclr(x)` are refused with `PARSE_PAREN_TOUCHES_WORD`, and `year:..2022(x)` is refused with it too, plus a `WARN_SYMBOLS_DROPPED` that reads `..2022` as a search word. In the other direction a `)` glued to a following filter field is accepted whatever the value: `(x)year:2020..2022`, `(x)year:2021` and `(x)venue:iclr` all parse, while `(x)year:..2022` fails with `FIELD_UNKNOWN_VALUE`. So which glued forms parse depends on the value's shape, and the open-range form fails for a reason that doesn't name the real cause.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A decision, recorded in spec 02 §Grammar and the query-grammar skill with its reason: either a filter clause glued to a parenthesis on either side is refused like a glued word, or spec 02 lists exactly which glued forms are accepted and why
- [ ] #2 A parametrized parse test pins the outcome (parse, or the error code and span) of each form in the description: `year:2020..2022(x)`, `year:2021(x)`, `year:..2022(x)`, `year:2020..(x)`, `venue:iclr(x)`, `(x)year:2020..2022`, `(x)year:2021`, `(x)year:..2022` and `(x)venue:iclr`, and every outcome matches the decision
- [ ] #3 An open year range glued to a parenthesis, either side, gets the diagnostic for the glued parenthesis (or parses, if the decision accepts it), never `FIELD_UNKNOWN_VALUE` or a `WARN_SYMBOLS_DROPPED` that reads the range as a search word
- [ ] #4 If a query that parses today becomes refused, the change follows spec 02 §Canonical form's QUERY_VERSION rule (a decision record on whether to bump it), and the generated editor lexer tables and golden are regenerated from lexer.py (codemirror-lezer skill) with the frontend editor tests passing
<!-- AC:END -->
