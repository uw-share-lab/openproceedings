---
id: TASK-105
title: Dedup joins PMLR and OpenReview records on the forum link from 2023
status: To Do
assignee: []
created_date: '2026-09-27 21:34'
labels:
  - ingest
milestone: m-4
dependencies: []
ordinal: 102000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
PMLR pages from v202 on carry the OpenReview forum link (v235 stored as the forum URL by TASK-053). Join on it before falling back to the title match.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Records sharing a forum id merge regardless of title differences,Table tests from the fixtures; dedup-rules skill updated
<!-- AC:END -->
