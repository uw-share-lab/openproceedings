---
id: TASK-260
title: >-
  Tidy two stale version mentions: setup-uv test fixture sha and 'FastAPI 0.141'
  wording
status: To Do
assignee: []
created_date: '2026-10-18 04:43'
labels:
  - tooling
  - docs
dependencies: []
priority: low
ordinal: 173000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by the 2026-10-17 Dependabot batch: .claude/scripts/tests/test-tooling-scripts.sh:534 fixture still pins the setup-uv v10.2.0 sha (harmless); .claude/skills/fastapi-conventions/SKILL.md:13 and spec 04 (about line 1336) say 'FastAPI 0.141', which reads as an as-built version but is a task-035 design note.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The fixture sha is either updated or commented as a deliberate old pin
- [ ] #2 The FastAPI version mentions are reworded so they don't read as the current version
<!-- AC:END -->
