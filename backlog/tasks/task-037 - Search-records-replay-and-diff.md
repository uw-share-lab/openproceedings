---
id: TASK-037
title: 'Search records, replay and diff'
status: Done
assignee:
  - '@search-records-keeper'
created_date: '2026-09-26 01:06'
updated_date: '2026-09-27 08:14'
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
- [x] #1 Record stores every field in spec 04's table; append-only SQLite
- [x] #2 Replay returns reproduced / drifted (with reason) / mismatch (logged API_REPLAY_MISMATCH) as HTTP 200
- [x] #3 GET /records/{id}/diff; tamper test yields mismatch, never drifted
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. openproceedings/records.py: ids_hash (known-answer), the append-only SQLite store (triggers, schema_version, WAL, connection per call), record ids.
2. api/pinned.py: load an older index_version read-only on demand (state.index_path validation, small LRU).
3. api/records.py: POST /records (re-runs search.run server-side), GET /records/{id} (replay: reproduced/drifted/mismatch), GET /records/{id}/diff; hook replay_status/require_citable for /export (TASK-036).
4. Contract tests: reproduced, drifted (changed snapshot; query_version), mismatch (wrong ids_hash, wrong excluded), diff, triggers, 422/404, no query text in logs.
5. Spec 04 as-built, search-records skill, CLAUDE.md layout.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
AC1: test_post_freezes_every_field_of_spec_04s_table (every table field + record_id, schema_version, ranking_params); unit test_update_and_delete_are_refused_by_the_triggers, test_an_existing_id_is_never_replaced (BEFORE INSERT trigger: SQLite REPLACE skips DELETE triggers unless recursive_triggers), test_concurrent_inserts_from_threads_each_get_their_own_row.
AC2: test_replay_on_the_same_index_is_reproduced, test_replay_loads_the_pinned_index_after_a_swap, test_a_changed_snapshot_with_the_pinned_index_gone_is_drifted_with_exact_counts (corpus drift, 1 added / 3 removed under the defaults), test_a_changed_query_version_is_drifted_and_membership_identical, test_a_tampered_record_is_a_mismatch_logged_once_never_drifted[ids_hash|excluded] (200, mismatch, exactly one ERROR API_REPLAY_MISMATCH).
AC3: diff tests (drifted with titles; titles from the pinned index when present; reproduced is empty); tamper test yields mismatch with changed == [].
Export hook for TASK-036: api.records.require_citable(request, record_id, engine) -> SearchRecord or 409 API_RECORD_MISMATCH (test_export_hook_refuses_a_mismatch_record_with_409 via a stand-in route); replay_status(request, record_id, engine).
Follow-ups NOT created on this branch (task ids would collide with the concurrent TASK-036/038 branches); file after the M3a merge: (1) op record save/replay CLI (spec 08 CLI table) over openproceedings.records; (2) semantic_version set when the near-miss panel is open (M5, with TASK-060/062); (3) TASK-065's op index retire should refuse via RecordStore.pinned(index_version).
Verified: uv run pytest 2538 passed, 1 skipped; make lint OK; make tooling OK.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
POST /records, GET /records/{id} (replay: reproduced/drifted/mismatch, all 200) and GET /records/{id}/diff. Core in openproceedings/records.py (ids_hash, SearchRecord, identify = search.run + match_ids, freeze, append-only RecordStore in <data_dir>/records.sqlite with UPDATE/DELETE/replace-refusing triggers, replay); api/records.py routes + the /export hook require_citable/replay_status; api/pinned.py loads older index versions read-only on demand via state.index_path. Spec 04 §Search records as-built, search-records skill, CLAUDE.md layout and a learning updated. Verified: uv run pytest 2538 passed / 1 skipped (16 contract + 25 unit record tests), make lint, make tooling.
<!-- SECTION:FINAL_SUMMARY:END -->
