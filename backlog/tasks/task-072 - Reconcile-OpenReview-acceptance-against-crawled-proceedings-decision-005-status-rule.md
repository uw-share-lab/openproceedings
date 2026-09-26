---
id: TASK-072
title: >-
  Reconcile OpenReview acceptance against crawled proceedings (decision-005
  status rule)
status: To Do
assignee: []
created_date: '2026-09-26 16:35'
labels:
  - ingest
milestone: m-4
dependencies:
  - TASK-021
  - TASK-052
  - TASK-053
ordinal: 71000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-005: where a venue-year's official proceedings are published and crawled, an OpenReview-accepted paper they don't list gets status=unknown plus a conflicts.csv row. Dedup can't decide it alone: it needs the crawled proceedings venue-years from the NeurIPS/PMLR miners. Found in the task-021 review (2026-09-26).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A reconcile step after dedup takes the crawled proceedings venue-years (from task-052/053 manifests) and sets unknown + a conflicts.csv row for OpenReview-accepted, unlisted papers
- [ ] #2 The derived status is a claim with its evidence, so dedup's inputs-equal-their-claims check and idempotence still hold
- [ ] #3 Unit and property tests; dedup-rules skill and decision-005 updated
<!-- AC:END -->
