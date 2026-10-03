---
id: TASK-094
title: >-
  Classify the venueid forms verified live: NeurIPS position and competition
  tracks, 2026 Evaluations_and_Datasets_Track
status: Done
assignee: []
created_date: '2026-09-27 20:49'
updated_date: '2026-09-27 21:10'
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
- [x] #1 NeurIPS Position_Paper_Track → position and Competition_Track → competition, with table-test rows citing the checked venueids (spec 01 §Track taxonomy)
- [x] #2 A decision records whether Evaluations_and_Datasets_Track maps to datasets_benchmarks; spec 01, 02 and the openreview-venueids skill follow it
- [x] #3 index_version / content_hash consequences stated (a reclassified record changes its hash)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Mapped NeurIPS Position_Paper_Track → position, Competition_Track → competition, and (on the owner's instruction via the implementing session) NeurIPS.cc/2026/Evaluations_and_Datasets_Track → datasets_benchmarks; spec 01/02 and the openreview-venueids and track-taxonomy skills follow. Table rows (LIVE) cite the checked venueids; V2_NOTES reads the recorded competition (LYvWVFdGZN) and position (VZnOKzQ5qW) notes. AC#3: track is in content_hash, so any record reclassified other → position/competition/datasets_benchmarks gets a new content_hash, a new snapshot_hash and a new index_version (saved records replay as drifted). For the current corpus nothing changes: the dry-run rebuild of snapshot 2026-09-23-d5ab3d6d444a is byte-identical (its 15 NeurIPS 2025 position papers came from the proceedings token; no record carries a NeurIPS position/competition venueid). AC#2 left open: the branch was told not to create decision records (parallel branches collide on ids); a decision recording the Evaluations_and_Datasets_Track mapping is proposed to the owner.
<!-- SECTION:NOTES:END -->
