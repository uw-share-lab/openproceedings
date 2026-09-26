---
id: TASK-037
title: 'Search records, replay and diff'
status: To Do
assignee: []
created_date: '2026-09-26 01:06'
labels:
  - api
milestone: m-3
dependencies:
  - TASK-035
ordinal: 36000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Spec 04 §Search records (search-records skill).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Record stores every field in spec 04's table; append-only SQLite
- [ ] #2 Replay returns reproduced / drifted (with reason) / mismatch (logged API_REPLAY_MISMATCH) as HTTP 200
- [ ] #3 GET /records/{id}/diff; tamper test yields mismatch, never drifted
<!-- AC:END -->
