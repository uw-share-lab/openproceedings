---
id: TASK-083
title: op record save / op record replay CLI over openproceedings.records
status: To Do
assignee: []
created_date: '2026-09-27 08:44'
labels:
  - cli
  - records
dependencies:
  - TASK-037
ordinal: 81000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Spec 08's CLI table lists `op record save "<q>" [--mode scholar]` and `op record replay <id>`: freeze a search as a search record with the same function as POST /api/v1/records (openproceedings.records.freeze + RecordStore.insert), and replay one with the same function as GET /records/{id} (openproceedings.records.replay), printing reproduced / drifted / mismatch. Found during task-037 (the core module was written so the CLI can call it).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 op record save writes a record to <data-dir>/records/records.sqlite identical in every field to what POST /records writes for the same query and index
- [ ] #2 op record replay prints the status and changed inputs, exits non-zero on mismatch (API_REPLAY_MISMATCH logged at ERROR) and zero otherwise (spec 08)
- [ ] #3 No query text in log lines; tests over the fixture index
<!-- AC:END -->
