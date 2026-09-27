---
id: TASK-090
title: 'API: identified_total and unclassified_total on /search and search records'
status: To Do
assignee: []
created_date: '2026-09-27 20:29'
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
