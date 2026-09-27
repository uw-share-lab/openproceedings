---
id: TASK-102
title: Expiry for the OpenReview raw-response cache
status: To Do
assignee: []
created_date: '2026-09-27 21:19'
labels:
  - ingest
milestone: m-4
dependencies: []
ordinal: 99000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Spec 01 calls for a cache expiry; today TASK-050's cache is only refreshed by hand with --refresh. Decide the TTL per listing type (accepted lists settle, submission lists change until decisions) and implement it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 TTL per listing type documented in spec 01,Expired entries are re-fetched and the refetch is logged,Tests with a fake clock
<!-- AC:END -->
