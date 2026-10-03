---
id: TASK-091
title: >-
  API additions for the UI: record index pin, replay-free record read, coverage
  citability, clause spans when not toggleable
status: Done
assignee: []
created_date: '2026-09-27 20:29'
updated_date: '2026-09-27 21:04'
labels:
  - api
milestone: m-3
dependencies: []
ordinal: 88000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
From TASK-033 design: (1) optional RecordRequest.index_version pin (save refuses 409 if the served index moved); (2) GET /records/{id}?replay=false returns the stored record without running a replay (readable while API_BUSY); (3) /coverage carries crawl_dates_kind and identification_citable; (4) /parse filters give the spans of the clauses behind a non-toggleable reason (nested/multiple/mixed) so the UI can point at them. All additive; spec 04; make openapi.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 RecordRequest.index_version (optional): a save when the served index is another is 409 API_INDEX_VERSION_UNAVAILABLE and saves nothing; malformed is 422
- [x] #2 GET /records/{id}?replay=false returns the stored record with replay null, runs nothing, costs one token, and is answered while every verification slot is taken
- [x] #3 /coverage snapshot carries crawl_dates_kind and identification_citable, derived exactly as a search record's
- [x] #4 /parse filters carry blocking_spans (code-point spans of the clauses behind multiple_clauses/nested/mixed_fields; empty otherwise)
- [x] #5 Spec 04 (and 02), skills, decision-014 for the replay nullability; make openapi; contract tests incl. an additive-only OpenAPI check against origin/dev
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
(1) The pin is checked first in create_record (before the parse, the verified charge and the save ceilings); RecordRequest.index_version has the /export pattern. (2) replay: bool = True; RecordResponse.replay is nullable (decision-014), and middleware.stored_read charges one token only for GET /records/{id} whose params are replay (false by pydantic's bool rule) and include, each once. (3) vocab.window_kind / crawl_dates_kind are shared by records.snapshot_facts and coverage.breakdown; a unit test compares them source by source. (4) query/clauses.py: blocking_spans are the written top-level conjuncts holding a filter of the field, for multiple_clauses/nested/mixed_fields; empty otherwise (validator); the golden file gained the field. Tests: backend/tests/contract/test_ui_additions.py, test_openapi_additive.py (additive vs origin/dev; the checker is tested on synthetic breaks), unit test_clauses.py/test_records.py/test_coverage.py. uv run pytest: 3803 passed, 2 skipped; npm test: 304 passed; make lint, make tooling green.

Implementation and verification finished. The worktree sandbox refused `backlog task complete`, so the status is left In Progress, which keeps make tooling green. To close: backlog task complete TASK-091.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Four additive /api/v1 changes for the UI: (1) POST /records takes an optional index_version pin; a save on a moved index is 409 API_INDEX_VERSION_UNAVAILABLE, saves nothing and spends no save. (2) GET /records/{id}?replay=false returns the stored record with replay null; it runs nothing, costs one token and is answered while API_BUSY (decision-014 covers the one nullability widening). (3) /coverage's snapshot gains crawl_dates_kind and identification_citable, derived by the same shared function a record uses. (4) /parse filters gain blocking_spans, the code-point spans of the clauses behind multiple_clauses, nested and mixed_fields. Spec 02 and spec 04, the skills and the design docs are updated; make openapi was run; there are contract tests for each change and an OpenAPI additive-only check against origin/dev.
<!-- SECTION:FINAL_SUMMARY:END -->
