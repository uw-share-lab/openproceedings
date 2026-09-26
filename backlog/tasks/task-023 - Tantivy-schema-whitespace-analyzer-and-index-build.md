---
id: TASK-023
title: 'Tantivy schema, whitespace analyzer and index build'
status: To Do
assignee: []
created_date: '2026-09-26 01:06'
labels:
  - engine
milestone: m-2
dependencies:
  - TASK-022
  - TASK-010
ordinal: 22000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Spec 03 §Index schema, §Tokenizer, §Versioning (tantivy-indexing, index-versioning skills).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Index fed pre-normalized text; analyzer only splits on whitespace
- [ ] #2 index_version = sha256(snapshot_hash, TOKENIZER_VERSION, SCHEMA_VERSION, ranking params)[:12]
- [ ] #3 data/indexes/<v>/ immutable; op index build < 2 min on the M4 corpus (bench)
<!-- AC:END -->
