---
id: TASK-108
title: Cited official paper counts per venue-year-track for the coverage gate
status: In Progress
assignee: []
created_date: '2026-09-27 22:46'
updated_date: '2026-09-27 23:41'
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
- [x] #1 docs/results/coverage-sources.md lists each count with its source URL and access date
- [ ] #2 official_counts.py filled and equal to it
- [ ] #3 The /coverage gate verdict appears for every cell with a count
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
coverage-sources.md written on t108 (off feat/m4-crawlers): 44 cells (ICLR/ICML/NeurIPS main 2013-2025, NeurIPS D&B 2021-2025), all sourced from public conference or proceedings pages, read 2026-09-27; disagreements listed in the doc. official_counts.py exists only on feat/m3b-ui, so AC #2 is still open: the literal for it is in the TASK-108 handoff and was checked equal to the doc with test_official_counts.py's own parser and check_table. AC #3 needs both branches merged. ICLR 2014/2015/2016 have official counts but no accepted-status source until TASK-096, so those gate cells will show a crawl gap. The original single AC was split into its three parts.
<!-- SECTION:NOTES:END -->
