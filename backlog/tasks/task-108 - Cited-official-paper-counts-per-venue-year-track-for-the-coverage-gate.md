---
id: TASK-108
title: Cited official paper counts per venue-year-track for the coverage gate
status: In Progress
assignee: []
created_date: '2026-09-27 22:46'
updated_date: '2026-09-28 02:05'
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
coverage-sources.md written on t108 (off feat/m4-crawlers): 44 cells (ICLR/ICML/NeurIPS main 2013-2025, NeurIPS D&B 2021-2025), all sourced from public conference or proceedings pages, read 2026-09-27; disagreements listed in the doc. official_counts.py exists only on feat/m3b-ui, so AC #2 is still open: integration must copy the corrected NeurIPS 2025 proceedings counts (5,286 main and 497 D&B, not the provisional 5,290/487) and test_official_counts.py must prove equality with this document. AC #3 needs both branches merged. TASK-096 now supplies ICLR 2014/2015/2016 accepted main records from the public ICLR archive, so their 35/31/80 official-count cells are no longer predicted crawl gaps. The original single AC was split into its three parts.
<!-- SECTION:NOTES:END -->
