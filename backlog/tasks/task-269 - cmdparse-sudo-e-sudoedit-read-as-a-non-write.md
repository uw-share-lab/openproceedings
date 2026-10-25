---
id: TASK-269
title: 'cmdparse: sudo -e / sudoedit read as a non-write'
status: In Progress
assignee:
  - '@jeevanparmar'
created_date: '2026-10-19 11:49'
updated_date: '2026-10-25 02:50'
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
- [x] #1 sudo -e, sudo --edit and sudoedit name their file arguments as writes
- [x] #2 Case-table rows for each, under data/indexes and backlog/
- [x] #3 make tooling and make mutate-changed: no survivors
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-24: cmdparse reads sudoedit as sudo -e with sudo's getopt (bundles, -u, --edit/--ed, --); each file is an Argv.creates write. -D dir: checked from both dirs. -R/--chroot with an edit is a ParseError (refused). enforce-backlog-cli covers file tools only, so the backlog/ rows are protect-data-dir's (its headers now say so). 24 rows; 15 mutants KILLED.
<!-- SECTION:NOTES:END -->
