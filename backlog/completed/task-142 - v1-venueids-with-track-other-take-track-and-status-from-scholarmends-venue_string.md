---
id: TASK-142
title: >-
  v1 venueids with track other take track and status from scholarmend's
  venue_string
status: Done
assignee:
  - '@jeevanp03'
created_date: '2026-09-30 04:30'
updated_date: '2026-09-30 05:23'
labels:
  - ingest
milestone: m-4
dependencies: []
ordinal: 124000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by TASK-098's review (2026-09-30). The RIS importer uses scholarmend's venue_string claim only when its track matches the venueid's; ICLR 2017's conference venueid (and ICLR 2023 BlogPosts) classify as track 'other', so strings like 'ICLR 2017 Poster' are always refused and those records stay status unknown with track other. The openreview-venueids skill says 2017's track comes from content.venue. No current RIS record is from 2017.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 For v1 venueids whose track is 'other', the importer takes track and status from venue_string when the venue and year agree (per the openreview-venueids table), with evidence
- [x] #2 Hand-written fixture cases (ICLR 2017 poster/oral/workshop, 2023 blogpost) and a real-data check
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
TDD: add ICLR 2017 poster/oral/workshop/rejected/another-year and ICLR 2023 blogpost rows to the v1 RIS fixture; take track from venue_string only for the table's no-track venueids (classify.V1_TRACK_FROM_VENUE: ICLR 2013/2017 lower-case conference) when venue and year agree; track claim carries the venue_string evidence; real-corpus byte-identical check vs origin/dev.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Scope: only the openreview-venueids table's no-track forms (ICLR.cc/2013/conference, ICLR.cc/2017/conference) take track from venue_string; other 'other' venueids (e.g. NeurIPS.cc/2022/Challenge/CellSeg) and suffixed forms keep other/unknown, so a string can never lift an out-of-taxonomy group into main. ICLR 2023 BlogPosts already classifies as track blogpost (_TRACKS, 2023+), so TASK-098's code already used 'Blogposts @ ICLR 2023'; the new fixture row pins it. decision-020 untouched (no ranking between v1 signals is introduced; the venue string is still the only RIS v1 status signal and a listing still decides acceptance per decision-005). Real data: data/cache/ris/out-covidence (1,391 read, 1,377 imported) and out-covidence-2020-2024 (443 read, 428 imported): repr of every record plus both ImportReports identical on origin/dev and the branch (sha256 14268ea2...); 0 venue_string claims, 0 ICLR 2013/2017 venueids.

Validation: make test 5,641 passed, 1 failed (test_openreview_v1_authors.py::test_a_split_always_has_the_id_count, Hypothesis too_slow health check under load average ~90 from parallel agents; unrelated file; passed 3 reruns and with the failing seed). make lint and make tooling pass.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
The RIS importer now takes track as well as status from scholarmend's venue_string claim for ICLR 2013/2017's lower-case conference venueid (classify.V1_TRACK_FROM_VENUE, the openreview-venueids table's no-track forms), when the string names the venueid's venue and year; the track claim carries the same 'venueid=... venue_string=...' evidence. Other 'other' venueids (e.g. NeurIPS.cc/2022/Challenge/CellSeg) and suffixed forms keep other/unknown. ICLR 2023 BlogPosts already classified as blogpost, so it already worked; a fixture row now pins it. Verified by new v1 fixture rows (ICLR 2017 poster/oral/workshop invitation/rejection/another-year string, 2023 blogpost), edit-based refusal tests and a classify guard test; real corpus (1,805 records) imports byte-identically vs origin/dev (0 venue_string claims, 0 ICLR 2013/2017 venueids).
<!-- SECTION:FINAL_SUMMARY:END -->
