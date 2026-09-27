---
id: TASK-082
title: Statuses indexed and per-source crawl dates for GET /coverage
status: To Do
assignee: []
created_date: '2026-09-27 08:02'
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
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Spec 01/07 name the source of 'statuses indexed' per venue-year
- [ ] #2 The snapshot manifest records crawl dates per source
- [ ] #3 GET /coverage serves both, additively, with contract tests
<!-- AC:END -->
