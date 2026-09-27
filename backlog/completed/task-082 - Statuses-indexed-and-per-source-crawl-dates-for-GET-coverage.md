---
id: TASK-082
title: Statuses indexed and per-source crawl dates for GET /coverage
status: Done
assignee: []
created_date: '2026-09-27 08:02'
updated_date: '2026-09-27 22:38'
labels:
  - api
  - ingest
milestone: m-3
dependencies: []
ordinal: 80000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Spec 07 §C asks, per venue-year, for the statuses its sources can contain (e.g. proceedings-only venue-years hold no rejected papers), and TASK-045's AC1 renders them on /coverage; spec 04's search records want crawl_dates per source. Neither is in the snapshot manifest today (only crawl_date/crawl_window over every fetch, and sources.ris reports without dates), so GET /coverage (TASK-038) serves neither. Decide where the per-source capability table lives (spec 01 source table or ingest/volumes-style table), record it in the manifest at snapshot build (FORMAT_VERSION question), and add it additively to CoverageResponse (coverage.breakdown).

Added by the TASK-038 review (2026-09-27): the TASK-045 coverage page also needs, per cell, the source, the official accepted count (official_accepted), delta and delta_pct against it, the ±1% M4 gate verdict (main-track and D&B cells with an official count only; spec 07 §C), and a citation for the official number (spec 05, coverage-reporting skill). Missing abstracts are per venue-year in the manifest today while spec 07 §C asks per cell, so record them per track too (a manifest FORMAT_VERSION question). Not implemented in TASK-038.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Spec 01/07 name the source of 'statuses indexed' per venue-year
- [x] #2 The snapshot manifest records crawl dates per source
- [x] #3 GET /coverage serves both, additively, with contract tests
- [x] #4 GET /coverage serves per cell: source, official_accepted, delta, delta_pct, the ±1% gate verdict (gated cells only) and the official count's citation
- [x] #5 The snapshot manifest records missing abstracts per track (per cell) and /coverage serves them; spec 07 §C's per-venue-year note is removed
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
As built (2026-09-27): statuses indexed come from ingest/sources.py (SOURCE_STATUSES per claim source; OPENREVIEW_FROM pinned to spec 01's OpenReview rows by test_sources.py): a venueid carries every status, a listing only accepted, RIS every status where OpenReview holds the venue-year and accepted before; plus any status the venue-year's records hold. Manifest FORMAT_VERSION 2 adds abstract_missing_by_track, sources_by_track, statuses_indexed and crawl_windows (per claim source). A format-1 manifest still loads: the load takes per-track facts from its verified record pass (coverage.TrackFacts) and statuses from the table; crawl_dates is then * only. A rebuild of the same inputs onto a format-1 directory is refused as for any format change. Official counts: official_counts.py (empty until sourced; test_official_counts.py holds it equal to docs/results/coverage-sources.md, which doesn't exist yet). New load-failure reason track_facts_mismatch. Additive only: test_openapi_additive.py passes against origin/dev.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
GET /coverage now serves, additively, per venue-year statuses_indexed and tracks (spec 07 §C cells: records, indexed_accepted, abstract_missing, sources, official_accepted/counts/citation/accessed, delta, delta_pct, gated, within_gate), and snapshot.crawl_dates gains a window per claim source (search records too). Snapshot manifest format 2 records per-track missing abstracts and sources, statuses indexed and per-source crawl windows; format-1 snapshots still serve (facts from the verified records). Specs 01, 04, 07, snapshots and coverage-reporting skills updated; spec 07's per-venue-year note removed. Official counts table is empty: no row until coverage-sources.md is written with citations.
<!-- SECTION:FINAL_SUMMARY:END -->
