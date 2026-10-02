---
id: TASK-172
title: >-
  enforce-pr-workflow reads its payload from stdin, not the HOOK_INPUT env var
  (TASK-156 follow-up)
status: To Do
assignee: []
created_date: '2026-10-02 10:33'
labels:
  - security
  - tooling
  - deferred
dependencies: []
references:
  - .claude/hooks/enforce-pr-workflow.sh
priority: low
ordinal: 142000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Source: TASK-156 review (PR #83, 2026-10-02), deferred. TASK-156 moved the other gates' payload to stdin so a command over ARG_MAX can't make exec fail. enforce-pr-workflow.sh still passes the payload to its Python step through the HOOK_INPUT environment variable; past ARG_MAX it falls back to a text check that fails closed, so it is safe but blocks commands it could have parsed. Pass the payload on stdin like the other gates.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 enforce-pr-workflow.sh passes the hook payload to Python on stdin (or a temp file), with no HOOK_INPUT variable
- [ ] #2 A case-table row with a payload over ARG_MAX is parsed and judged normally (allowed when it should be), and the existing rows pass
- [ ] #3 `make tooling` and `python3 .claude/scripts/mutate.py --changed` pass
<!-- AC:END -->
