---
id: TASK-012
title: 'Parser to AST with precedence, warnings and errors'
status: In Progress
assignee:
  - '@jeevan'
created_date: '2026-09-26 01:06'
updated_date: '2026-09-26 02:08'
labels:
  - query
milestone: m-1
dependencies:
  - TASK-011
ordinal: 11000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
EBNF of spec 02 → typed AST (Or, And, Not, Term, Phrase, Near, Wildcard, Filter).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 NOT > AND > OR; mixed AND/OR at one level parses and raises WARN_MIXED_AND_OR
- [x] #2 All-negative query is an error; unbalanced parens, empty groups, bad ranges are errors with spans
- [x] #3 Wildcard stem < 3 chars is an error (per task-001's decision on $)
- [x] #4 Golden (decision-001): `gpt-4*` parses as Phrase[gpt, Wildcard(4*)]; `"large language model$"` as a Phrase whose last element is a Wildcard
<!-- AC:END -->
