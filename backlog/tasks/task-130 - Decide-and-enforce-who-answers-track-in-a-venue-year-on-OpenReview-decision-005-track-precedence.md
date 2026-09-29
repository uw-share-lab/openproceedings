---
id: TASK-130
title: >-
  Decide and enforce who answers track in a venue-year on OpenReview
  (decision-005 track precedence)
status: To Do
assignee:
  - '@jeevanp03'
created_date: '2026-09-29 23:23'
labels:
  - dedup
  - decision
dependencies: []
ordinal: 114000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-005 says proceedings answer track only for venue-years not on OpenReview. TASK-072 (2026-09-29) did not enforce it: on the real crawl 151 records in venue-years on OpenReview take their track from the proceedings, and setting them to unknown would drop ICLR 2016 main from 80 to 0 (OpenReview holds only its workshop track) and ICLR 2014 main to 34/35. Needs the owner's decision: does 'on OpenReview' mean the venue-year or the venue-year's track, and what is a listing's track when OpenReview holds the track but not the paper. decision-005 §Track in an OpenReview venue-year records the question.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The owner's answer is recorded in decision-005 (or a superseding decision)
- [ ] #2 dedup/reconcile enforce it with unit and property tests; the real-crawl effect per gated cell is listed
<!-- AC:END -->
