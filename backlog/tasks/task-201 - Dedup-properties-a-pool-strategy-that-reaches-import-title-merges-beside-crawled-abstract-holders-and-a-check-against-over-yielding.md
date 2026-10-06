---
id: TASK-201
title: >-
  Dedup properties: a pool strategy that reaches import title merges beside
  crawled abstract holders, and a check against over-yielding
status: To Do
assignee: []
created_date: '2026-10-06 04:43'
labels:
  - ingest
  - dedup
  - testing
milestone: m-4
dependencies: []
ordinal: 144000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The gate on the v0.2.0 nightly fix (2026-10-06, PR for fix/dedup-yield-property) found that test_dedup_props.py's decision-045 property detects a broken yield rule only through its @examples: with them removed, mutations 'never yield' and 'a partner with any abstract keeps the merge' pass all 2,000 ci examples, because the generic pool strategy rarely puts same-title imports next to crawled records holding their abstract (the nightly needed 50,000 examples). The property also checks only one direction: a rule that yields too often (any instead of all) passes every test.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A pool strategy (or a targeted one) reaches decision-045's shapes at the ci profile: the two mutations above fail the property without its @examples
- [ ] #2 A test or property fails when the import yields although a title partner holds its abstract
<!-- AC:END -->
