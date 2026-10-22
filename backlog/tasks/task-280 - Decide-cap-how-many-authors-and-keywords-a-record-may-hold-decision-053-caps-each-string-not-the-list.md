---
id: TASK-280
title: >-
  Decide: cap how many authors and keywords a record may hold (decision-053 caps
  each string, not the list)
status: In Progress
assignee:
  - '@jeevan'
created_date: '2026-10-22 05:32'
updated_date: '2026-10-22 19:01'
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

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. caps.py: MAX_AUTHORS=500, MAX_KEYWORDS=200 (owner, 2026-10-22); an over-cap list keeps its first N on the record and every claim, flagged by a decision-054 note before any decision-053 note; is_trimmed reads it.
2. snapshot.RecordFile: lists_cut (id -> {field: count the source listed}) from the winning claim's note.
3. Exports: BibTeX 'and others'; RIS one N1 (no sentinel AU); CSV lists_cut column (last); JSONL lists_cut only on a cut record. Plumbed like twins (cli, api/export, api/compare).
4. Tests at count-1, count, count+1 for both; export tests.
5. decision-054, spec 01, spec 04, record-schema/bibtex/ris skills; results doc with the read-only check over 2026-10-16-03eab0ef56c4.
<!-- SECTION:PLAN:END -->
