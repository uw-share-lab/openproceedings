---
id: TASK-114
title: Crawler tidy-up after the HTTP unification
status: To Do
assignee: []
created_date: '2026-09-27 23:24'
labels:
  - ingest
milestone: m-4
dependencies: []
ordinal: 111000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Follow-ups from TASK-103 and TASK-105: (1) move the per-source ingest loop (lock, crawl, write marker) into sources/common beside the shared replay; (2) delete the per-source HTTP-property tests in test_fetch.py and test_openreview_client.py that test_http.py now covers once for all sources; (3) make pmlr._forum call urls.forum_id so there is one forum-id parser. Behaviour-preserving: test_combined_snapshot.py's pinned hashes must not change.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 One ingest loop in common used by all four sources,Duplicate HTTP-property tests removed with test_http.py covering each property,pmlr uses urls.forum_id,test_combined_snapshot hashes unchanged
<!-- AC:END -->
