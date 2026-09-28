---
id: TASK-115
title: Reconcile M3b's per-source status table with M4 when both reach dev
status: To Do
assignee: []
created_date: '2026-09-27 23:56'
labels:
  - ingest
milestone: m-4
dependencies: []
ordinal: 111000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
M3b (TASK-082) added ingest/sources.py (statuses_indexed, per-source status table) while M4 has an ingest/sources/ package: rename M3b's module (done on M3b as ingest/statuses.py), then at the dev merge: replace status_check.py's local table with M3b's statuses_indexed (drop the present argument), correct its OpenReview year table (ICLR on API v1 2013, 2014, 2016-2023, not from 2018) from the v1 adapters and openreview_v2's first v2 year, and consider saving unexpected_statuses in manifest format 2.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 One per-source status table used by coverage and status_check,ICLR 2013-2017 OpenReview years correct and pinned by a test against the adapters,Coverage consistency check and status_check both pass on the combined snapshot
<!-- AC:END -->
