---
id: TASK-065
title: 'Deploy: compose, Caddy TLS, index promotion runbook'
status: To Do
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-09-26 19:07'
labels:
  - ops
milestone: m-6
dependencies:
  - TASK-064
  - TASK-046
ordinal: 64000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Spec 08 §Deploy (release-manager).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 docker compose up serves api + web over TLS
- [ ] #2 Index promotion and op index retire documented and tested
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
From the task-023 review (2026-09-26): a Tantivy index directory must be writable to open (readers take .tantivy-meta.lock), so an index can't be served from a read-only mount as built; the deploy needs a writable volume, or an overlay, for data/indexes/<v>/ (files stay read-only and hash-verified).
<!-- SECTION:NOTES:END -->
