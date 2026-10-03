---
id: TASK-090
title: 'API: identified_total and unclassified_total on /search and search records'
status: Done
assignee: []
created_date: '2026-09-27 20:29'
updated_date: '2026-09-27 21:04'
labels:
  - api
milestone: m-3
dependencies: []
ordinal: 87000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
From TASK-033 design (docs/design/2026-09-27-export-records-and-paper.md): the methods text needs 'identified N' and the unclassified count without the UI adding numbers. Add additive fields identified_total (= total + excluded.total, from the identification_ast) and unclassified_total (unknown track + unknown status buckets) to SearchResponse and ReplayInfo/SearchRecord responses; spec 04; make openapi. Blocks TASK-044.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 SearchResponse carries identified_total (total + excluded.total, the identification_ast count) and unclassified_total (track unknown + status unknown), additive and required in the schema
- [x] #2 A search record and its replay carry both (record: derived on read, never stored; replay: null when refused)
- [x] #3 Tests hold each equal to the identified/unclassified numbers op search and op record save print
- [x] #4 Spec 04 and the api-contract skill describe them; make openapi regenerated; the OpenAPI diff against origin/dev is additive
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Shared helpers engine/exclusions.py::identified_total and unclassified_total, called by op search / op record save and by the API (SearchResponse top-level pair; SearchRecord computed fields, excluded from the stored body via records.DERIVED; ReplayInfo pair, null when refused). Verified: test_search.py compares both to op search's printed identified/unclassified for every query x sort; test_ui_additions.py holds identified_total == |match_ids(identification_ast)| and record/replay/search equal op record save's printout; test_openapi_additive.py: additive vs origin/dev. uv run pytest: 3803 passed, 2 skipped; npm test --workspace frontend: 304 passed; make lint, make tooling green.

Implementation and verification finished. The worktree sandbox refused `backlog task complete`, so the status is left In Progress, which keeps make tooling green. To close: backlog task complete TASK-090.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
identified_total and unclassified_total are on /search, on a search record (derived when it is read, never stored) and on its replay (null when refused). They come from the helpers op search prints with, and contract tests hold them equal to the CLI's counts. The change is additive: the OpenAPI check against origin/dev passes. Spec 04 and the api-contract and search-records skills are updated.
<!-- SECTION:FINAL_SUMMARY:END -->
