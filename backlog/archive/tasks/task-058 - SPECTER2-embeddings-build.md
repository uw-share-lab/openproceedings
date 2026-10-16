---
id: TASK-058
title: SPECTER2 embeddings build
status: To Do
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-09-29 23:58'
labels:
  - semantic
  - deferred
milestone: m-5
dependencies:
  - TASK-054
ordinal: 57000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Spec 06 §Model and storage (specter2-embeddings skill).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Model and adapter pinned by revision; semantic_version
- [ ] #2 data/embeddings/<index_version>/<semantic_version>.npy + .json sidecar
- [ ] #3 Disabled with a notice on any version mismatch
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Deferred (2026-09-29, decision-017): v1 is Boolean search only; the semantic layer is phase 2 and off the v1 release path. Kept, not deleted; resume only under a decision that supersedes decision-017.
<!-- SECTION:NOTES:END -->
