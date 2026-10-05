---
id: TASK-189
title: 'Dedup: the title step never consults the abstract'
status: To Do
assignee: []
created_date: '2026-10-05 08:39'
labels:
  - ingest
  - dedup
milestone: m-4
dependencies: []
ordinal: 133000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found reviewing TASK-179 (no real instance today): an import whose title lost a symbol can equal a different paper's title key in the same venue-year (-Guard beside a note titled Guard) and merges on title though its abstract is another record's. Also, a forum-id RIS row and a proceedings-id RIS row with one title and different long abstracts now merge.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Either a title-step merge of an import is refused when its own-page abstract matches a different record of the cell, or the cases are documented as accepted with their reason; tests for both shapes
<!-- AC:END -->
