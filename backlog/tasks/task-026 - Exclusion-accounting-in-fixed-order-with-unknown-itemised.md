---
id: TASK-026
title: Exclusion accounting in fixed order with unknown itemised
status: To Do
assignee: []
created_date: '2026-09-26 01:06'
labels:
  - engine
milestone: m-2
dependencies:
  - TASK-024
  - TASK-014
ordinal: 25000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Spec 03 §Exclusion accounting (default-filters, prisma-reporting skills).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Buckets assigned track first then status; sum equals excluded.total
- [ ] #2 unknown itemised separately; only default filters count
- [ ] #3 Golden cases for overlap (rejected workshop paper counts once under track.workshop)
<!-- AC:END -->
