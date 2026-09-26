---
id: TASK-018
title: 'PaperRecord model, content_hash and provenance claims'
status: To Do
assignee: []
created_date: '2026-09-26 01:06'
labels:
  - ingest
milestone: m-2
dependencies:
  - TASK-009
ordinal: 17000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Spec 01 §Record schema (record-schema skill).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 pydantic v2 model with every spec 01 field; id scheme op:<venue>:<year>:<native>
- [ ] #2 content_hash over searchable and filterable fields only (provenance excluded)
- [ ] #3 Claims ledger per field (source, url, fetched_at, evidence)
<!-- AC:END -->
