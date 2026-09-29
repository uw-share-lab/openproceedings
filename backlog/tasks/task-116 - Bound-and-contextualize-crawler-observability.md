---
id: TASK-116
title: Bound and contextualize crawler observability
status: In Progress
assignee:
  - '@jeevanp03'
created_date: '2026-09-28 01:59'
updated_date: '2026-09-29 14:40'
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
- [x] #1 Record-level anomalies are DEBUG and each listing/crawl retains one aggregate WARNING with counts
- [x] #2 OpenReview v1/v2 emit start and at-most-30-second progress heartbeats with venue, year, API, processed counts, requests and cache hits
- [x] #3 HTTP policy event names are selected from fixed constants rather than dynamically constructed strings
- [x] #4 Public-projection refusals identify the safe canonical request target without response data or credentials
- [x] #5 Proceedings parser budget failures identify the source URL and give refresh/cache recovery guidance
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Built 2026-09-29. AC1: per-record WARNINGs demoted to DEBUG (openreview_unknown_track, openreview_v1_unmapped/_conflict/_duplicate, neurips_record_invalid, pmlr_record_invalid; the proceedings ones gain url); one aggregate WARNING per listing/crawl (listing_attention; openreview_crawl_attention, v1 now also counts duplicate and invalid, both carry api). AC2: openreview_v2.Progress logs openreview_crawl_started and openreview_crawl_progress (common.Heartbeat, at most every 30 s on the client's monotonic clock; api, venue, year, notes_read, forums (v1), imported, skipped, requests, cached) for v1 and v2. AC3: http.PolicyEvents constants (CRAWL_EVENTS, openreview_client.EVENTS) replace Policy.log_prefix; an AST test refuses a built crawler event name. AC4: _public_projection takes the canonical URL and every refusal names GET <url> (the cache key), never response data or credentials. AC5: html.HTMLBudgetError(SourceError, ValueError, reason html_budget) names the page URL, --refresh for an index page and the cache entry (http.cache_name) for a paper page; every miner passes the URL. Docs: logging-standards §Crawl lines, openreview-api skill, spec 01 (cache expiry, Crawl logs). Not changed: *_cache_expired stays INFO per entry and openreview_cache_incompatible stays WARNING per entry (not record-level anomalies).
<!-- SECTION:NOTES:END -->
