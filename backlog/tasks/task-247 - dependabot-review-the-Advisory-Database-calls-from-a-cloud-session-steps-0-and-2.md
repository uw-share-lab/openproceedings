---
id: TASK-247
title: >-
  dependabot-review: the Advisory Database calls from a cloud session (steps 0
  and 2)
status: To Do
assignee: []
created_date: '2026-10-14 01:13'
labels:
  - tooling
  - ci
dependencies: []
references:
  - decision-048
  - TASK-243
ordinal: 173000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The GitHub Advisory Database calls /dependabot-review makes (gh api advisories?ecosystem=...&affects=..., step 0's uv query and step 2's per-package queries) are a path outside repos/, so a Claude Code cloud session's proxy may refuse them with its HTTP 403 'sessions are bound to their configured repositories' (TASK-243 probe, 2026-10-13, session cse_01Q24cxnP5Nu3yXGC2FKjWqW, which did not try them). Until decided, the procedure fails closed: a refused step 2 query is a hard stop for that PR (check couldn't run), a refused step 0 uv query goes under 'for the owner' (decision-048, TASK-243 AC3/AC6 addendum). Can't be done yet: it needs a cloud session to probe the call.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A cloud session's answer to gh api 'advisories?ecosystem=npm&affects=next&per_page=1' is recorded (status and message)
- [ ] #2 If refused: the owner decides whether step 2 keeps the hard stop, relies on npm audit --package-lock-only and the release notes, or another source; decision-048 and the procedure record it
- [ ] #3 If it answers: the procedure's TASK-247 caveats are removed
<!-- AC:END -->
