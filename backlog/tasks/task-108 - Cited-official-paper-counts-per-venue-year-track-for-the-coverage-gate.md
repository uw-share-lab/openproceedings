---
id: TASK-108
title: Cited official paper counts per venue-year-track for the coverage gate
status: To Do
assignee: []
created_date: '2026-09-27 22:46'
labels:
  - ingest
  - docs
milestone: m-4
dependencies: []
ordinal: 105000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-082's official_counts.py is empty and a test pins it to docs/results/coverage-sources.md, which doesn't exist; so every /coverage cell shows no official count and the ±1% gate never runs. Collect official accepted counts (main, D&B) per venue-year 2013+ with a citation each.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 docs/results/coverage-sources.md lists each count with its source URL and access date,official_counts.py filled and equal to it,The /coverage gate verdict appears for every cell with a count
<!-- AC:END -->
