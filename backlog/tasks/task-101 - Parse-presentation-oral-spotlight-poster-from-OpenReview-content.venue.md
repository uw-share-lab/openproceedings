---
id: TASK-101
title: Parse presentation (oral/spotlight/poster) from OpenReview content.venue
status: To Do
assignee: []
created_date: '2026-09-27 21:19'
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
- [ ] #1 Per-venue-year table of verified content.venue strings with fixture-backed table tests,Unrecognised strings give unknown and are logged,Spec 01 and the record schema document the field
<!-- AC:END -->
