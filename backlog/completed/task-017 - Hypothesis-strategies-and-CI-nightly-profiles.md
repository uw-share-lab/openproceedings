---
id: TASK-017
title: Hypothesis strategies and CI/nightly profiles
status: Done
assignee:
  - '@jeevan'
created_date: '2026-09-26 01:06'
updated_date: '2026-09-26 03:33'
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

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
tests/strategies.py (asts, negative_asts, leaves, filters, queries over the fixture vocabulary, n-grams and real prefixes) and tests/unit/test_properties.py; ci 2,000 / nightly 50,000 with every property in the nightly workflow; counterexamples kept as golden rows; a coverage guard keeps properties non-vacuous. Cap-adjacent stems carried to task-057.
<!-- SECTION:FINAL_SUMMARY:END -->
