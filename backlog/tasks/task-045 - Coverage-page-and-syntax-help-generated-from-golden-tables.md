---
id: TASK-045
title: Coverage page and syntax help generated from golden tables
status: To Do
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-09-27 20:27'
labels:
  - frontend
milestone: m-3
dependencies:
  - TASK-038
  - TASK-039
  - TASK-082
ordinal: 44000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Spec 05 §Pages (research-dataviz skill).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 /coverage renders API data with statuses indexed; no hard-coded numbers
- [ ] #2 /help/syntax generated from the spec 02 golden table
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Design (TASK-033, 2026-09-27): docs/design/2026-09-27-coverage-and-syntax-help.md + copy deck §8. /coverage: every number an API field, no client sums (track x status detail per row from cells, '–' for no cell); 'Collected <from> to <to>' until /coverage exposes the window kind. API gap for the main session: additive snapshot.crawl_dates_kind and identification_citable on /coverage. /help/syntax: anchors are diagnostic codes in lower case (Help ▸ links build from the code; #slow-clauses for the two API_ codes); Messages section lists every reader-facing code with example, registry message and fix (a test fails on a missing code); Limits from /meta; generate from a committed JSON of the goldens checked by a backend contract test like wrap-golden.json.

Pre-pass: each help example carries its mode; the link reads 'Search with this example' (S15, Nit 7).
<!-- SECTION:NOTES:END -->
