---
id: TASK-195
title: 'Comparison: a citable, copyable summary and a place in the search record'
status: To Do
assignee: []
created_date: '2026-10-05 08:56'
labels:
  - frontend
  - api
  - ux
milestone: m-3
dependencies: []
ordinal: 139000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
A comparison's counts (kept, dropped, not in the index, added) live only on screen and in the downloaded CSVs; nothing nudges Save search record and no record stores that a comparison was made. The gate's usability and methodology reviews (2026-10-05) asked what a methods section may cite: the group counts and comparisons are search-development aids, never flow-diagram numbers, and a comparison figure needs the reviewer's own file hash and date beside the index_version and canonical_hash.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The panel offers a copyable sentence stating the counts, index_version, canonical_hash, the file's sha256 and the date, worded per prisma-reporting; whether a search record should note a comparison is decided and recorded
<!-- AC:END -->
