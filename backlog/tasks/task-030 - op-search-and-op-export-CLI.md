---
id: TASK-030
title: op search and op export CLI
status: To Do
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-09-26 03:40'
labels:
  - engine
  - api
milestone: m-2
dependencies:
  - TASK-025
  - TASK-026
  - TASK-027
ordinal: 29000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Spec 08 §CLI.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 op search supports --mode scholar, --explain, --engine tantivy|reference, --ids
- [ ] #2 op export --format ris|csv|bibtex|jsonl streams the full set ordered by id
- [ ] #3 The Trust-Evals Most Updated string runs end to end on the M2 snapshot
- [ ] #4 CLI prints diagnostics to stderr as user output (not logging); at most one search_run INFO line with the same privacy-safe fields as the API access log
<!-- AC:END -->
