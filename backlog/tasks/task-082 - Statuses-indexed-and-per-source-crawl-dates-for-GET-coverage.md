---
id: TASK-082
title: Statuses indexed and per-source crawl dates for GET /coverage
status: To Do
assignee: []
created_date: '2026-09-27 08:02'
updated_date: '2026-09-27 08:20'
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
- [ ] #1 Spec 01/07 name the source of 'statuses indexed' per venue-year
- [ ] #2 The snapshot manifest records crawl dates per source
- [ ] #3 GET /coverage serves both, additively, with contract tests
- [ ] #4 GET /coverage serves per cell: source, official_accepted, delta, delta_pct, the ±1% gate verdict (gated cells only) and the official count's citation
- [ ] #5 The snapshot manifest records missing abstracts per track (per cell) and /coverage serves them; spec 07 §C's per-venue-year note is removed
<!-- AC:END -->
