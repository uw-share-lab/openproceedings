---
id: TASK-059
title: sort=semantic within the matched set
status: To Do
assignee: []
created_date: '2026-09-26 01:06'
labels:
  - semantic
milestone: m-5
dependencies:
  - TASK-058
ordinal: 58000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Spec 06 §Features 1.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Order by cosine to the top-20 BM25 centroid; ties by BM25 then id
- [ ] #2 Membership identical to sort=relevance
<!-- AC:END -->
