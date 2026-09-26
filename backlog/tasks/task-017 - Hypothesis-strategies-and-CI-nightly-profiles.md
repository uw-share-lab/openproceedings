---
id: TASK-017
title: Hypothesis strategies and CI/nightly profiles
status: In Progress
assignee:
  - '@jeevan'
created_date: '2026-09-26 01:06'
updated_date: '2026-09-26 03:12'
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
- [x] #1 ci profile 2,000 examples, nightly 50,000; deadlines set
- [x] #2 Every counterexample found is saved as a golden case
- [x] #3 Strategies cover phrases, NEAR, wildcards, filters and NOT
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Stems near the 200-expansion cap need the 5k fixture: carried by task-057 (differential@50k).
<!-- SECTION:NOTES:END -->
