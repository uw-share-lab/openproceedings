---
id: TASK-021
title: Deduplication with merges.csv and conflicts.csv
status: In Progress
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-09-26 16:52'
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
Implemented in backend/src/openproceedings/ingest/dedup.py. Step 1 merges identical ids (same forum id + venue + year, or same proceedings id); a forum id in two venue-years is a venue_year_not_merged conflict. Step 2 merges (venue, year, token-contract title key) only across disjoint source sets; never two forum ids, never two proceedings ids (from native ids and urls.* claims, ingest/urls.py), never a non-proceedings track into a proceedings listing (proceedings source or proceedings id, so RIS listings count); chains that would fold two papers are refused whole (title_key_chain). Keys come from kept claims only, so a second run changes nothing. Fields re-resolved from the union of claims by PRECEDENCE (decision-005 as data, amended for RIS and same-source claims); same-source repeats keep the newest (newest:/tie: rows for every field); cross-source rows for status, track and the title key. Merge/Conflict rows for merges.csv/conflicts.csv (task-022 writes them). Properties at ci and nightly: idempotent (records + precedence rows), order-independent, conservation, never folds two papers; colliding pools + a chains strategy + @example rows for the review's two over-merges. The decision-005 'OpenReview-accepted but unlisted' rule is task-072 (needs 052/053). Real corpus (local, 2026-09-26): 1805 RIS records from the two searches -> 1805, no merges, no conflicts.

Verification round (2026-09-26): proceedings-id records must name themselves in a URL claim, so merged records keep absorbed listing ids (fixes a second-run over-merge); a listing's own unknown track (PMLR v235/v267) no longer blocks ICML merges; NeurIPS URLs up to 2021 and upper-case hex parse; ties broken by exact JSON; not-merged rows judged on output records, so reruns repeat them.
<!-- SECTION:NOTES:END -->
