---
id: TASK-017
title: Hypothesis strategies and CI/nightly profiles
status: To Do
assignee: []
created_date: '2026-09-26 01:06'
labels:
  - engine
  - query
milestone: m-1
dependencies:
  - TASK-013
ordinal: 16000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Strategies for tokens, query strings and ASTs over a corpus vocabulary (property-testing skill).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 ci profile 2,000 examples, nightly 50,000; deadlines set
- [ ] #2 Every counterexample found is saved as a golden case
- [ ] #3 Strategies cover phrases, NEAR, wildcards, filters and NOT
<!-- AC:END -->
