---
id: TASK-038
title: GET /coverage
status: Done
assignee:
  - '@api-engineer'
created_date: '2026-09-26 01:06'
updated_date: '2026-09-27 08:08'
labels:
  - api
milestone: m-3
dependencies:
  - TASK-035
ordinal: 37000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Counts per venue × year × track × status, statuses indexed, missing abstracts, snapshot date (spec 04, 07 §C).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Numbers match the snapshot manifest exactly
- [x] #2 Contract test
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Serve the snapshot manifest's venue x year x track x status breakdown (the same numbers the snapshot build computed; docs/results corpus report was read from it) via a shared openproceedings/coverage.py; verify the snapshot via Papers' RecordFile pass; cache per index_version; contract tests vs an independent count over records.jsonl and the index doc count.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Numbers come from the snapshot manifest (the counts the corpus report was read from), reshaped by the shared openproceedings/coverage.py::breakdown; no CLI/report function computed the breakdown before (docs/results/2026-09-27-corpus.md was read by hand from manifest.json). Follow-up TASK-082: statuses indexed per venue-year and per-source crawl dates (not in the manifest).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
GET /api/v1/coverage: the three versions, snapshot (name, hash, crawl_date, crawl_from/to, built_at, sources), totals and venue_years (records, abstract_missing, unknown_track, unknown_status, cells {track,status,count} in vocabulary order, unknown last and never folded). Numbers are the served index's snapshot manifest via coverage.breakdown, verified through Papers.records (records hash) and against the index document count; any inconsistency is a 500 API_INTERNAL. Cached once per index_version (task-080 memo rule, last 2 kept). Contract tests: counts vs an independent count of records.jsonl, totals = index doc_count, exact manifest match (AC1), versions, byte-stable order, hot swap + compute-once log, 503, missing/tampered snapshot 500s; unit tests for breakdown. Spec 04 as-built and CLAUDE.md updated.
<!-- SECTION:FINAL_SUMMARY:END -->
