---
id: TASK-053
title: PMLR miner and ICML volume table
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
ordinal: 52000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
ICML 2013-2022 primary (v28, v32, v37, v48, v70, v80, v97, v119, v139, v162; decision-013) and confirmation of 2023+ (v202, v235, v267) (pmlr-proceedings skill).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Volume table in config, each row with a source; unknown volumes never coerced to ICML
- [ ] #2 Competition/workshop volumes classified correctly
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
TASK-002 verified each ICML volume's heading and paper count (pmlr-proceedings skill table); add v28-v97 to the volume config; NeurIPS competition volumes v123/v133/v176/v220 need a NeurIPS table (ICML_PMLR_VOLUMES is ICML-only). v235 paper entries link OpenReview forum ids. Fixtures: backend/tests/fixtures/http/pmlr/.
<!-- SECTION:NOTES:END -->
