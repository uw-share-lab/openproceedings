---
id: TASK-022
title: Snapshot build and diff with manifest
status: To Do
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-09-26 16:07'
labels:
  - ingest
milestone: m-2
dependencies:
  - TASK-019
  - TASK-020
  - TASK-021
ordinal: 21000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Spec 01 §Pipeline step 5 (snapshots skill).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 records.jsonl sorted by id; manifest with counts, sources, crawl dates, dedup counts, snapshot_hash
- [ ] #2 Same inputs → byte-identical output (determinism test)
- [ ] #3 op snapshot diff reports added/removed/changed records
- [ ] #4 op snapshot build takes the RIS inputs (spec 01's op ingest ris <mended.ris>...; resolved.json beside each) and writes each file's ImportReport (read, imported, skipped by reason, abstract_missing, status) into the manifest
<!-- AC:END -->
