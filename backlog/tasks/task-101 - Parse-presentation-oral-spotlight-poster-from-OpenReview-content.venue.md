---
id: TASK-101
title: Parse presentation (oral/spotlight/poster) from OpenReview content.venue
status: In Progress
assignee:
  - '@jeevanp03'
created_date: '2026-09-27 21:19'
updated_date: '2026-09-30 00:48'
labels:
  - ingest
milestone: m-4
dependencies: []
ordinal: 98000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The v2 crawler (TASK-050) takes track and status from content.venueid only. content.venue carries the presentation type (e.g. 'ICLR 2024 oral'); parse it with a per-venue-year table of the exact strings, unknown otherwise.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Per-venue-year table of verified content.venue strings with fixture-backed table tests,Unrecognised strings give unknown and are logged,Spec 01 and the record schema document the field
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Field reused: `presentation` (oral/spotlight/poster/null) already existed (TASK-123 v1 vocabulary); shape unchanged, so RECORD_SCHEMA_VERSION stays 3 (content_hash excludes presentation).

Table: `classify.V2_PRESENTATION` ((venue, year) -> content.venue -> (track its venueid must give, presentation)), built from every distinct content.venue in the real v2 crawl cache (ICLR 2024-25, ICML 2023-25, NeurIPS 2023-25) plus the recorded ICLR 2026 Poster fixture. Looked up only for accepted, non-workshop notes (workshop strings are per-workshop free text; rejected/withdrawn never take a presentation). OralPoster -> oral, spotlightposter -> spotlight. Known-no-presentation (null, not counted): BT@ICLR2024, Tiny Papers @ ICLR 2024 {Archive,Present,Notable}, ICLR 2025 Blogpost Track, NeurIPS 2024 Competition Track, NeurIPS 2025 Position Paper Track. Unmapped -> null, DEBUG openreview_presentation_unmapped (forum id only), per-venue-year count presentation_unmapped in report/manifest, openreview_crawl_finished and the one openreview_crawl_attention WARNING. Known unmapped: ICML 2026 regular (recorded); ICLR 2026 Oral / ICML 2026 spotlight lack recorded notes.

Fixtures: 17 notes-presentation-*.json, one note per string, trimmed from the crawl cache (public projection) and run through scrub.py. scrub.py's email regex rewrote BT@ICLR2024; now requires a dotted domain (regression test). test_combined_snapshot hashes re-recorded (records now carry presentation).

Real data (scratch OP_DATA_DIR, cache symlinked; base = origin/dev built the same way): presentation_unmapped = 0 for all 8 v2 venue-years; ids, content_hash and every non-presentation field identical to base; op eval coverage identical (PASS 43/44, ICLR 2013 accepted exception). Checks: pytest 5422 passed/2 skipped, make lint, make tooling green.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
v2 crawler now sets presentation from content.venue via an exact per-venue-year table (classify.V2_PRESENTATION), fixture-backed per string; unmapped strings are null and counted per venue-year. Verified: tests, lint, tooling; real-cache snapshot has 0 unmapped and an unchanged coverage gate.
<!-- SECTION:FINAL_SUMMARY:END -->
