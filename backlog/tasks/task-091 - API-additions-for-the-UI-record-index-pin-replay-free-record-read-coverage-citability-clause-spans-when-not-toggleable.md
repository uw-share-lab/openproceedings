---
id: TASK-091
title: >-
  API additions for the UI: record index pin, replay-free record read, coverage
  citability, clause spans when not toggleable
status: To Do
assignee: []
created_date: '2026-09-27 20:29'
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
