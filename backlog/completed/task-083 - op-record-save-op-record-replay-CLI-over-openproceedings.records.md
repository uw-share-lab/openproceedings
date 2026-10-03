---
id: TASK-083
title: op record save / op record replay CLI over openproceedings.records
status: Done
assignee: []
created_date: '2026-09-27 08:44'
updated_date: '2026-09-27 18:13'
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
- [x] #1 op record save writes a record to <data-dir>/records/records.sqlite identical in every field to what POST /records writes for the same query and index
- [x] #2 op record replay prints the status and changed inputs, exits non-zero on mismatch (API_REPLAY_MISMATCH logged at ERROR) and zero otherwise (spec 08)
- [x] #3 No query text in log lines; tests over the fixture index
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Tests first (backend/tests/contract/test_record_cli.py; unit parse tests). 2. api.records.replay_info shared by GET /records/{id} and the CLI. 3. cli: op record save (parse -> index_path selection -> records.freeze -> RecordStore.insert with ApiConfig's store limits) and op record replay (own index first via IndexState.pinned's rule, else --index/current; records.replay without admit). 4. Spec 08, spec 04, README, search-records skill.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Decisions: (a) exit codes follow spec 08 and AC #2, not a distinct code for drift: 0 reproduced or drifted, 3 mismatch (cli.EXIT_MISMATCH), 1 unknown or malformed id, or no index to replay on. (b) The CLI passes no admit: the verified-clause cap and candidate ceiling are API serving policy (decision-010), as are the rate limit and save ceilings, so a CLI replay is never withheld; the store size cap and free-space floor apply with ApiConfig defaults. (c) --index is current or an index_version under <data-dir>/indexes (api.state.index_path), never a directory, and a directory not named for its index is refused: a record pins a version a replay must find by name. (d) --data-dir is the global op option (op --data-dir X record ...), as for every other command. (e) GET /records/{id} replay block and op record replay --json share api.records.replay_info.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
op record save / op record replay implemented over openproceedings.records (freeze + RecordStore.insert; replay), --json replay block shared with GET /records/{id} via api.records.replay_info. Exit 0 reproduced/drifted, 3 mismatch, 1 unknown id or no index. CLI applies the store size cap and free-space floor but not the serving limits (a CLI replay is never withheld). Verified: backend/tests/contract/test_record_cli.py (API-equality of the saved record, replay matrix, subprocess exit codes, store floor, no query text in logs) and unit parse tests; full uv run pytest 3533 passed, make lint and make tooling green.
<!-- SECTION:FINAL_SUMMARY:END -->
