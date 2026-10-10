---
id: TASK-227
title: >-
  A drifted search record explains each removed paper: moved to another track,
  or no longer in the index
status: To Do
assignee: []
created_date: '2026-10-10 16:33'
labels:
  - api
  - frontend
  - records
dependencies: []
ordinal: 157000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
From the fix/aaai-aies-tracks review gate (review-methodologist S1, 2026-10-10). When a saved record replays as drifted, its removed list gives only id and title, so a reviewer cannot tell that a paper moved to student_abstract, iaai or demo (decision-050) rather than being deleted. Add each removed entry's current track (or 'not in the index') and a per-cause tally to the records diff route and the record page. Owner: milestone C (feat/new-venues-c), which is changing the records API and record page now; a precondition of the v0.3.0 release.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The records diff route gives each removed id's current track or 'not in the index', and a per-cause tally
- [ ] #2 The record page shows the same, in plain language
- [ ] #3 Contract and frontend tests pin both; done before v0.3.0 is tagged
<!-- AC:END -->
