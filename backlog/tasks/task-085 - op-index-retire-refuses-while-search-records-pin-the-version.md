---
id: TASK-085
title: op index retire refuses while search records pin the version
status: To Do
assignee: []
created_date: '2026-09-27 08:44'
labels:
  - cli
  - records
  - ops
dependencies:
  - TASK-065
ordinal: 83000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Spec 08 lists `op index retire <index_version>` (planned, task-065): it must refuse while any search record pins the version, since a deleted pinned index turns those records into permanent drifted. openproceedings.records.RecordStore(<data-dir>/records).pinned(index_version) returns the count (task-037).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 op index retire refuses (non-zero exit, count reported, no files touched) when RecordStore.pinned(v) > 0
- [ ] #2 Retires as before when no record pins v; test both
- [ ] #3 release-manager agent and index-versioning skill updated
<!-- AC:END -->
