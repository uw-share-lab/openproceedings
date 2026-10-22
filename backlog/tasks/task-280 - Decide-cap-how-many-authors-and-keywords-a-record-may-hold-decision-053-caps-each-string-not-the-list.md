---
id: TASK-280
title: >-
  Decide: cap how many authors and keywords a record may hold (decision-053 caps
  each string, not the list)
status: To Do
assignee: []
created_date: '2026-10-22 05:32'
labels:
  - ingest
  - security
dependencies: []
priority: low
ordinal: 186000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Follow-up from TASK-279. decision-053 caps the length of each author name (1,000 characters) and each keyword (2,000) at ingest, but not how many a record holds. A source can still send any number of names or keywords, and each is stored in the snapshot and written into every export and API response. Snapshot 2026-10-16-03eab0ef56c4 holds at most 95 authors and 54 keywords on one record (TASK-279 notes). Decide whether to cap the count at ingest (trim and flag, as decision-026 and decision-053 do, or refuse), at what numbers, and what a trimmed author list means for exports (BibTeX's 'and others', RIS), or record why not.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A decision record says whether the number of authors and keywords per record is capped, at what counts, and how an over-cap list is handled and flagged, or why it is left uncapped
- [ ] #2 If capped: ingest/caps.py applies it with tests at count-1, count and count+1, and spec 01 and the record-schema skill describe it
<!-- AC:END -->
