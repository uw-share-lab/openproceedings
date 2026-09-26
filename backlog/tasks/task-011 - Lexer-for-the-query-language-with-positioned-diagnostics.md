---
id: TASK-011
title: Lexer for the query language with positioned diagnostics
status: To Do
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-09-26 01:51'
labels:
  - query
milestone: m-1
dependencies:
  - TASK-010
  - TASK-001
ordinal: 10000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Tokens for uppercase operators, |, -, phrases, fields, ranges, * and $ wildcards, NEAR/n (spec 02 §Grammar).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Lowercase and/or/not are terms; WARN_LOWERCASE_OPERATOR emitted
- [ ] #2 Every error carries a half-open code-point span over q and a fix hint
- [ ] #3 Property test: random strings never raise, only return diagnostics
- [ ] #4 Golden (decision-001): `a$`/`ab*` → stem-too-short error; `"large language model$"` lexes a wildcard inside a phrase
<!-- AC:END -->
