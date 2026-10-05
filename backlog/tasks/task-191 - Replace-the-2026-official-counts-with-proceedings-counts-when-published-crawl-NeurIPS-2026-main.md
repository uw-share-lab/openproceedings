---
id: TASK-191
title: >-
  Replace the 2026 official counts with proceedings counts when published; crawl
  NeurIPS 2026 main
status: To Do
assignee: []
created_date: '2026-10-05 08:39'
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
