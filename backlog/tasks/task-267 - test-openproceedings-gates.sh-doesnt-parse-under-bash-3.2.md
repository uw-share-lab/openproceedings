---
id: TASK-267
title: test-openproceedings-gates.sh doesn't parse under bash 3.2
status: In Progress
assignee:
  - '@jeevanparmar'
created_date: '2026-10-19 11:49'
updated_date: '2026-10-25 02:50'
labels:
  - hooks
  - tooling
dependencies: []
priority: low
ordinal: 174000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
/bin/bash -n (macOS bash 3.2.57) fails at line 413: syntax error near '(' in an embedded Python line (bad = [f"{f}: ..." for ...]), so the table can't run with the system bash on a Mac. CI and make tooling use a newer bash.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The table parses and passes under bash 3.2 (or the Makefile and docs say it needs bash 4+, and make tooling refuses an older one with that message)
- [x] #2 make tooling green
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-24: bash 3.2 misparses a quoted heredoc containing ( inside $(...); the program is read into SAME_PATTERN first. Table under /bin/bash 3.2: 1738 passed. Follow-up done in-branch: check_old_bash.py runs bash -n with /bin/bash 3.x in make tooling (30 files; skips elsewhere).
<!-- SECTION:NOTES:END -->
