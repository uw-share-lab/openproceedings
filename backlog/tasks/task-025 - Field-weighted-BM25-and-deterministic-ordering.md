---
id: TASK-025
title: Field-weighted BM25 and deterministic ordering
status: To Do
assignee: []
created_date: '2026-09-26 01:06'
labels:
  - engine
milestone: m-2
dependencies:
  - TASK-024
ordinal: 24000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Spec 03 §Ranking (field-weighted-bm25 skill).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 title 2.0 / abstract 1.0, k1 1.2, b 0.75; params in index_version
- [ ] #2 All sorts tie-break by id; same query + index → identical order and scores
- [ ] #3 Negations and filters never score
<!-- AC:END -->
