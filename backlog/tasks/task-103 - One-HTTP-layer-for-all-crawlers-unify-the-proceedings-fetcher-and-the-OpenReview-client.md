---
id: TASK-103
title: >-
  One HTTP layer for all crawlers: unify the proceedings fetcher and the
  OpenReview client
status: To Do
assignee: []
created_date: '2026-09-27 21:34'
updated_date: '2026-09-27 23:11'
labels:
  - ingest
milestone: m-4
dependencies: []
ordinal: 100000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-050 and TASK-052/053 were built in parallel and each has its own fetcher and cache: sources/http.py (Fetcher, PageCache, sleep/clock callables, FetchError) and sources/openreview_client.py (OpenReviewClient on scholarmend's Cache, Clock protocol, OpenReviewError). Each has its own pacing, 429/5xx retries, Retry-After/ratelimit-reset parsing, atomic cache writes, URL canonicalisation, transport, crawl markers/replay (common.write_marker + crawl.load_crawls vs openreview_v2.crawl_file/cached_crawls/replay), per-crawl report types writing crawl_window, and interval defaults. Unify into one transport/clock/retry/cache layer with the OpenReview auth on top, without changing any recorded behaviour.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 One Transport/Response/Clock abstraction and one retry/backoff implementation used by all three sources,One crawl-marker/replay mechanism and one report type feeding the manifest crawl_window,One error hierarchy handled once in cli.main and snapshot,Existing fixture tests pass unchanged (behaviour-preserving); snapshot build output byte-identical on the fixtures
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
From TASK-105: make pmlr._forum call urls.forum_id so there is one forum-id parser.
<!-- SECTION:NOTES:END -->
