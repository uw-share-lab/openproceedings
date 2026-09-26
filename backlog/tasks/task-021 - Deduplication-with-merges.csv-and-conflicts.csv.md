---
id: TASK-021
title: Deduplication with merges.csv and conflicts.csv
status: In Progress
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-09-26 16:20'
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
- [x] #1 Never merges across venue/year, on (title, ""), or two OpenReview records with different forum ids
- [x] #2 Cross-source title matching (OpenReview ↔ proceedings ↔ RIS) only
- [x] #3 Property tests: idempotent, order-independent
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented in backend/src/openproceedings/ingest/dedup.py: step 1 merges identical ids (same forum id + venue + year, or same proceedings id; a forum id in two venue-years is a venue_year_not_merged conflict); step 2 merges (venue, year, token-contract title key) only across disjoint source sets, never two forum ids, never a non-proceedings track into proceedings; chains that would fold two same-source records are refused whole. Fields re-resolved from the union of claims by PRECEDENCE (decision-005 as data); inputs must equal their own claims' resolution. merges.csv / conflicts.csv rows as Merge / Conflict tuples (writing them is task-022). Properties (test_dedup_props.py, ci profile 2000): idempotent, order-independent, conservation, no cross venue/year, distinct forum ids never share a record. Real corpus (local, 2026-09-26): 1805 RIS records from the two searches -> 1805, no merges, no conflicts.
<!-- SECTION:NOTES:END -->
