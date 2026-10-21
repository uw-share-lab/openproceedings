---
id: TASK-269
title: 'cmdparse: sudo -e / sudoedit read as a non-write'
status: To Do
assignee: []
created_date: '2026-10-19 11:49'
labels:
  - hooks
  - security
dependencies: []
priority: low
ordinal: 176000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
cmdparse treats sudo -e <file> (sudoedit) as running no write, so the gates that judge writes (protect-data-dir, enforce-backlog-cli) don't see it edit the file. Security-gate Nit on the 0.4.0 promotion; already on main.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 sudo -e, sudo --edit and sudoedit name their file arguments as writes
- [ ] #2 Case-table rows for each, under data/indexes and backlog/
- [ ] #3 make tooling and make mutate-changed: no survivors
<!-- AC:END -->
