---
id: TASK-061
title: Membership invariant test and recall@25 evaluation
status: To Do
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-09-29 23:58'
labels:
  - semantic
  - eval
  - deferred
milestone: m-5
dependencies:
  - TASK-060
  - TASK-059
ordinal: 60000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Spec 06 §Evaluation (near-miss-evaluator).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 CI: /search totals, ids and exports identical with the layer on/off
- [ ] #2 op eval near-miss recall@25 beats the BM25-OR baseline, or the feature doesn't ship
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Deferred (2026-09-29, decision-017): v1 is Boolean search only; the semantic layer is phase 2 and off the v1 release path. Kept, not deleted; resume only under a decision that supersedes decision-017.
<!-- SECTION:NOTES:END -->
