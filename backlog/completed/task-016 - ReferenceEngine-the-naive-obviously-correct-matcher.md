---
id: TASK-016
title: 'ReferenceEngine: the naive, obviously-correct matcher'
status: Done
assignee:
  - '@jeevan'
created_date: '2026-09-26 01:06'
updated_date: '2026-09-26 03:33'
labels:
  - engine
milestone: m-1
dependencies:
  - TASK-014
ordinal: 15000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Evaluates the AST directly over normalized token positions (reference-oracle skill); shares no code with the Tantivy compiler.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Terms, phrases (per field), NEAR/n (unordered, per field), wildcards over a vocabulary, filters, NOT
- [x] #2 200-record golden query fixture: every query's expected id set passes
- [x] #3 Never imported by api/ (import-lint test)
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
engine/protocol.py (types only) and engine/reference.py: the definition of matching, wildcards expanded once per query with the 200 cap, per-field phrases and unordered NEAR, facets per decision-001 rule 6; import isolation tested; 44 golden queries on a 200-record fixture agree with an independent evaluator.
<!-- SECTION:FINAL_SUMMARY:END -->
