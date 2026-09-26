---
id: TASK-024
title: AST → Tantivy compilation
status: To Do
assignee: []
created_date: '2026-09-26 01:06'
labels:
  - engine
milestone: m-2
dependencies:
  - TASK-023
  - TASK-016
ordinal: 23000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Spec 03 §AST → Tantivy compilation (ast-compilation skill).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Phrases never cross fields; NOT without a positive clause gets an explicit all-docs clause
- [ ] #2 Wildcards expand via the term dictionary; list returned; >200 is an error
- [ ] #3 NEAR multi-token fallback verifies positions; filters are non-scoring
- [ ] #4 op search --explain prints the compiled query
<!-- AC:END -->
