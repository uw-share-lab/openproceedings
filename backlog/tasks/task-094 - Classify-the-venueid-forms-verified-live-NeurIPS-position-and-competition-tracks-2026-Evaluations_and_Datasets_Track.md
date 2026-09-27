---
id: TASK-094
title: >-
  Classify the venueid forms verified live: NeurIPS position and competition
  tracks, 2026 Evaluations_and_Datasets_Track
status: To Do
assignee: []
created_date: '2026-09-27 20:49'
labels:
  - ingest
  - classify
milestone: m-4
dependencies: []
priority: high
ordinal: 91000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-002's live check (docs/research/2026-09-27-openreview-and-proceedings-facts.md) confirmed venueids that classify.py's _TRACKS table does not map: NeurIPS.cc/<Y>/Position_Paper_Track (2025+, 40 accepted in 2025) and NeurIPS.cc/<Y>/Competition_Track (2024+) both classify as 'other' today, which hides them from the default filter. NeurIPS renamed D&B to NeurIPS.cc/2026/Evaluations_and_Datasets_Track for 2026; whether it is datasets_benchmarks needs a spec 01/02 decision.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 NeurIPS Position_Paper_Track → position and Competition_Track → competition, with table-test rows citing the checked venueids (spec 01 §Track taxonomy)
- [ ] #2 A decision records whether Evaluations_and_Datasets_Track maps to datasets_benchmarks; spec 01, 02 and the openreview-venueids skill follow it
- [ ] #3 index_version / content_hash consequences stated (a reclassified record changes its hash)
<!-- AC:END -->
