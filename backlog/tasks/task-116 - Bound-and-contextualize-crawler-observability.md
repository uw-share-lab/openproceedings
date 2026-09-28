---
id: TASK-116
title: Bound and contextualize crawler observability
status: To Do
assignee: []
created_date: '2026-09-28 01:59'
labels:
  - ingest
  - observability
milestone: m-4
dependencies: []
references:
  - backend/src/openproceedings/ingest/sources/openreview_v1.py
  - backend/src/openproceedings/ingest/sources/openreview_v2.py
  - backend/src/openproceedings/ingest/sources/http.py
  - backend/src/openproceedings/ingest/sources/openreview_client.py
  - backend/src/openproceedings/ingest/sources/html.py
priority: medium
type: enhancement
ordinal: 112000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The M4 review found that the crawler reports durable aggregate outcomes well, but long OpenReview runs lack bounded heartbeats and several low-level failures lack source context. Item-level warnings can also flood logs on degraded corpora. Consolidate crawler logging so full-corpus runs stay diagnosable without high-cardinality noise.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Record-level anomalies are DEBUG and each listing/crawl retains one aggregate WARNING with counts
- [ ] #2 OpenReview v1/v2 emit start and at-most-30-second progress heartbeats with venue, year, API, processed counts, requests and cache hits
- [ ] #3 HTTP policy event names are selected from fixed constants rather than dynamically constructed strings
- [ ] #4 Public-projection refusals identify the safe canonical request target without response data or credentials
- [ ] #5 Proceedings parser budget failures identify the source URL and give refresh/cache recovery guidance
<!-- AC:END -->
