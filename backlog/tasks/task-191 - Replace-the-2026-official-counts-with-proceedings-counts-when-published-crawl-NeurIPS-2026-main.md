---
id: TASK-191
title: >-
  Replace the 2026 official counts with proceedings counts when published; crawl
  NeurIPS 2026 main
status: To Do
assignee: []
created_date: '2026-10-05 08:39'
updated_date: '2026-10-05 08:56'
labels:
  - ingest
  - eval
milestone: m-4
dependencies: []
ordinal: 135000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
coverage-sources.md's ICML 2026 main row (6,341) is a count of the conference's own paper list minus its position listing, and ICLR 2026's (5,357) is the fact sheet's; rule 1 prefers the proceedings index. NeurIPS 2026's main conference was not public on OpenReview on 2026-10-05, so the index holds only its workshops; its Evaluations_and_Datasets_Track and position strings have no classifier rows yet. The skipped ICLR 2026 Workshop/Re-Align group should be checked live for another venue id.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The ICML row is replaced from the PMLR volume and the ICLR row from proceedings.iclr.cc once each exists; NeurIPS 2026 main, D&B and position are crawled, classified with recorded fixtures and gated; Re-Align is resolved or explained
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-05 (gate, track-classifier-auditor): the ICLR 2026 proceedings index already exists and was counted that day (5,351 Conference entries at proceedings.iclr.cc/paper_files/paper/2026, equal to the index), so the ICLR row is rule 1 now. What remains: the ICML 2026 PMLR volume, NeurIPS 2026 main / D&B / position, and Workshop/Re-Align. NeurIPS 2026 on OpenReview also holds 95 Creative_AI_Track notes (other, unknown) beside its workshops.
<!-- SECTION:NOTES:END -->
