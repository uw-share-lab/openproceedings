---
id: TASK-215
title: >-
  New venues milestone C: OpenAlex abstract fallback for AAAI, AIES and FAccT,
  the abstract_kind field and filter (index schema 4)
status: To Do
assignee: []
created_date: '2026-10-10 03:47'
labels:
  - ingest
  - query
  - new-venues
milestone: m-4
dependencies: []
ordinal: 148000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Milestone C of docs/plans/2026-10-09-new-venues-design.md: sources/openalex.py fills abstracts only where no official one exists (new venues only), abstract_kind (official|openalex|none) derived field, the abstract_kind: filter on index schema 4 (SchemaForm flag, 422 on a schema-3 index), coverage and export labels, and an audit of OpenAlex against official abstracts.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 No official abstract is ever replaced; NeurIPS/ICLR/ICML untouched
- [ ] #2 abstract_kind: filters identically in Tantivy and the reference matcher
- [ ] #3 OpenAlex fidelity audit written to docs/results
<!-- AC:END -->
