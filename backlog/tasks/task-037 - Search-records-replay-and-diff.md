---
id: TASK-037
title: 'Search records, replay and diff'
status: To Do
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-09-27 08:04'
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

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
From TASK-036 (export): GET /export does not accept record_id yet. Wire it in api/export.py::pinned_engine (the documented hook): record_id -> the record's index_version (then IndexState.pinned), 422 API_BAD_PARAM if both record_id and index_version are given or record_id is malformed, 404 API_RECORD_NOT_FOUND, 409 API_RECORD_MISMATCH when its replay status is mismatch — all before the first byte. Spec 04 §Testing wants 'An export with record_id of a mismatch record returns 409 and streams nothing'. Update backend/tests/contract/test_export.py::test_the_openapi_document_describes_the_export (param set) and tick TASK-036 AC#3.
<!-- SECTION:NOTES:END -->
