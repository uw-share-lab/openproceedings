---
id: TASK-021
title: Deduplication with merges.csv and conflicts.csv
status: To Do
assignee: []
created_date: '2026-09-26 01:06'
labels:
  - ingest
milestone: m-2
dependencies:
  - TASK-018
  - TASK-003
ordinal: 20000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Spec 01 §Pipeline step 4 (dedup-rules skill).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Never merges across venue/year, on (title, ""), or two OpenReview records with different forum ids
- [ ] #2 Cross-source title matching (OpenReview ↔ proceedings ↔ RIS) only
- [ ] #3 Property tests: idempotent, order-independent
<!-- AC:END -->
