---
id: TASK-132
title: >-
  Dedup: NeurIPS 2021 'Stochastic Online Linear Regression' stays split because
  a third OpenReview note shares its title
status: To Do
assignee: []
created_date: '2026-09-30 00:39'
labels:
  - dedup
milestone: m-4
dependencies: []
ordinal: 115000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by the TASK-054 coverage report (docs/results/2026-09-29-coverage.md, snapshot 2026-09-29-4cd2bba17cad, index b170674bcf49): NeurIPS 2021 main is 2,335 indexed vs 2,334 official (+1, within ±1%). The +1 is one paper counted twice. 'Stochastic Online Linear Regression: the Forward Algorithm to Replace Ridge' is in the index as op:neurips:2021:rDdb26AQ0SO (OpenReview v1 only, accepted) and op:neurips:2021:nips-cca289d2a4acd14c1cd9a84ffb41dd29 (NeurIPS proceedings only, accepted). Dedup refuses to merge them because OpenReview also has op:neurips:2021:W6e384Lkjbw (status unknown) under the same title, so the title group is ambiguous. Reconcile (TASK-072) skipped NeurIPS 2021 because its D&B listing states no count, so the unmerged OpenReview note is not demoted either.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Investigate W6e384Lkjbw: what the note is (a duplicate, a withdrawn or earlier submission, another paper) and why its status is unknown
- [ ] #2 Fix the dedup or reconcile rule so the pair merges, or document why it stays split (spec 01 / dedup-rules skill)
- [ ] #3 Check the real-data effect: rebuild from the real cache and record NeurIPS 2021 main's indexed count and any other cell that changes
<!-- AC:END -->
