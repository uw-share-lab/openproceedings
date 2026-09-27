---
id: TASK-073
title: Highlights within the 50-hit page budget
status: To Do
assignee: []
created_date: '2026-09-26 21:07'
updated_date: '2026-09-26 21:27'
labels:
  - engine
milestone: m-3
dependencies:
  - TASK-027
  - TASK-035
  - TASK-031
ordinal: 72000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
task-027 review: highlighting a 50-hit page with ~400-word abstracts costs ~174 ms (tokenize is 164 ms of it), ~1.3 s at 3,000 words, against spec 03's 100 ms p95 for a search returning 50 hits. Where highlights are computed is the API's page-assembly decision (task-035): precompute each record's token offsets at index build (in the stored record, a SCHEMA_VERSION bump) or cache tokenize per (index_version, id).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A 50-hit page's highlights fit the spec 03 budget at 80k (measured by task-031's benchmark)
- [ ] #2 Spans are identical to engine/highlight.py's for every golden query
<!-- AC:END -->
