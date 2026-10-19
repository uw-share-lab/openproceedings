---
id: TASK-260
title: >-
  Tidy two stale version mentions: setup-uv test fixture sha and 'FastAPI 0.141'
  wording
status: Done
assignee: []
created_date: '2026-10-18 04:43'
updated_date: '2026-10-19 00:01'
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
- [x] #1 The fixture sha is either updated or commented as a deliberate old pin
- [x] #2 The FastAPI version mentions are reworded so they don't read as the current version
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
check_uv_pin rows' fixture UVA now uses the workflows' current pin (setup-uv v10.3.0, 1c37ad07, from #161), with a comment that any sha would do (the check compares the uv version, not the sha). fastapi-conventions SKILL.md and spec 04 §As built now say FastAPI keeps the route path relative to the declaring router, as found on 0.141 when task-035 built the API, so neither reads as the current version (uv.lock has 0.143.0).

Review round 1: backend/src/openproceedings/api/app.py's module docstring said the same 'FastAPI 0.141' and is reworded the same way; the reworded lines rewrapped; the fixture comment no longer names a version.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
The check_uv_pin fixture uses the workflows' setup-uv pin, with a comment that any sha would do. The FastAPI route-path note in the fastapi-conventions skill, spec 04 and api/app.py says it was found on 0.141 by task-035, not that 0.141 is current.
<!-- SECTION:FINAL_SUMMARY:END -->
