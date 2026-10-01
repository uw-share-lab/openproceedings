---
id: TASK-065
title: 'Deploy: compose, Caddy TLS, index promotion runbook'
status: To Do
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-10-01 07:49'
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
- [ ] #2 Index promotion documented and tested; the runbook covers retire (implemented in TASK-085)
- [ ] #3 The api container mounts, read-only, a directory that holds only `withheld.txt` (an empty file on a fresh instance: `op serve` off loopback, or behind a trusted proxy, refuses to load without it; TASK-067), never `log.jsonl`, and not the file alone (an editor that saves by rename would leave the container reading the old list across SIGHUP); it runs neither as root nor as the operator account that owns the log (source: TASK-136 deferral and TASK-067 review; spec 08 §Deploy, the takedown-log bullet)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
From the task-023 review (2026-09-26): a Tantivy index directory must be writable to open (readers take .tantivy-meta.lock), so an index can't be served from a read-only mount as built; the deploy needs a writable volume, or an overlay, for data/indexes/<v>/ (files stay read-only and hash-verified).
<!-- SECTION:NOTES:END -->
