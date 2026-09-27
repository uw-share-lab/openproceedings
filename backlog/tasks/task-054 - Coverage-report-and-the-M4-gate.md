---
id: TASK-054
title: Coverage report and the M4 gate
status: To Do
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-09-27 21:19'
labels:
  - eval
milestone: m-4
dependencies:
  - TASK-048
  - TASK-049
  - TASK-051
  - TASK-052
  - TASK-053
ordinal: 53000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Spec 07 §C (coverage-reporting skill).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 docs/results/coverage-sources.md cites one official count per gated cell
- [ ] #2 Every main/D&B cell with an official count within ±1%; statuses-indexed column
- [ ] #3 op eval coverage regenerates the dated report
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
TASK-002 count checks (2026-09-27): NeurIPS 2021 main proceedings 2,334 vs OpenReview v1 venues 2,630 'accepted' (2,286 poster + 284 spotlight + 60 oral) — unexplained, resolve before gating; NeurIPS 2024 main 4,034 vs 4,035. Equal: NeurIPS 2022-23 main and D&B, 2024 D&B, 2021 D&B rounds; ICML 2023-2025 PMLR vs OpenReview. Rejected counts are complete only for ICLR (decision-012).

From TASK-050: check each live crawl's counts against the venue's published numbers (the openreview-crawler agent's 1% rule) here, not in the crawler.
<!-- SECTION:NOTES:END -->
