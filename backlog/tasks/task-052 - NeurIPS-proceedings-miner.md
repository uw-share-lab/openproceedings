---
id: TASK-052
title: NeurIPS proceedings miner
status: To Do
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-09-27 20:42'
labels:
  - ingest
milestone: m-4
dependencies:
  - TASK-022
  - TASK-002
ordinal: 51000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
proceedings.neurips.cc main and D&B (neurips-proceedings skill).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 ≤2023 Datasets_and_Benchmarks alias handled
- [ ] #2 Cross-checks OpenReview acceptance; conflicts to conflicts.csv
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
TASK-002: 1987-2021 main URLs have no track token (-Abstract.html; classify_proceedings('') is unknown, so main comes from host+year); 2022-23 token Datasets_and_Benchmarks, 2024 _Track; 2021 D&B on datasets-benchmarks-proceedings.neurips.cc (round1 66, round2 108). 2025 main/D&B not published on 2026-09-27 (only 64 Creative AI). Crawl from 2013 (decision-013). Fixtures: backend/tests/fixtures/http/neurips/.
<!-- SECTION:NOTES:END -->
