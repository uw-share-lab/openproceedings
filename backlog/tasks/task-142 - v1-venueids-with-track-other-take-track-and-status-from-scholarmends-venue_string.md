---
id: TASK-142
title: >-
  v1 venueids with track other take track and status from scholarmend's
  venue_string
status: To Do
assignee:
  - '@jeevanp03'
created_date: '2026-09-30 04:30'
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
- [ ] #1 For v1 venueids whose track is 'other', the importer takes track and status from venue_string when the venue and year agree (per the openreview-venueids table), with evidence
- [ ] #2 Hand-written fixture cases (ICLR 2017 poster/oral/workshop, 2023 blogpost) and a real-data check
<!-- AC:END -->
