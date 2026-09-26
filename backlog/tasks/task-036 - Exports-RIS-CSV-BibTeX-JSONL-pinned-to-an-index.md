---
id: TASK-036
title: 'Exports: RIS, CSV, BibTeX, JSONL pinned to an index'
status: To Do
assignee: []
created_date: '2026-09-26 01:06'
labels:
  - api
milestone: m-3
dependencies:
  - TASK-035
  - TASK-004
ordinal: 35000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Spec 04 §Exports (ris-format, bibtex-format skills).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 RIS imports into Covidence (one manual fixture) and round-trips through venuetriage's parser
- [ ] #2 BibTeX parses with refaudit; note carries provenance
- [ ] #3 X-Total and X-Index-Version headers; record_id or index_version pins the source index
<!-- AC:END -->
