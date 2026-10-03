---
id: TASK-103
title: >-
  One HTTP layer for all crawlers: unify the proceedings fetcher and the
  OpenReview client
status: Done
assignee: []
created_date: '2026-09-27 21:34'
updated_date: '2026-09-27 23:24'
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
- [x] #1 One Transport/Response/Clock abstraction and one retry/backoff implementation used by all three sources,One crawl-marker/replay mechanism and one report type feeding the manifest crawl_window,One error hierarchy handled once in cli.main and snapshot,Existing fixture tests pass unchanged (behaviour-preserving); snapshot build output byte-identical on the fixtures
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
From TASK-105: make pmlr._forum call urls.forum_id so there is one forum-id parser.
Baseline first (commit 38167aa): test_combined_snapshot.py builds one snapshot offline from recorded v2 (ICLR 2024) + v1 (ICLR 2021, 2015 gap) + NeurIPS 2013 + PMLR v28/v235 crawls; snapshot_hash ff71377d8f7d1e7cbbd3d0797e758588e3039886481c7aa58c1eb10cd4db9df4, whole-directory hash 9c8e9f9cdbbfc3302e18aad12fbd10b185eceb1606774d24088153a13567a15f, both unchanged after the refactor. A cache written by the pre-refactor code (scholarmend {key,payload} OpenReview entries, fixture-shaped proceedings pages, old markers) rebuilt the same snapshot byte for byte with the new code.
Shape: http.py is the one layer (Request/Response/Transport(request, timeout)/Clock, urllib_transport with no redirects and a body cap, canonical(), retry_after(), Policy, ResponseCache + per-source codec keeping both on-disk layouts, HttpClient.send/through_cache, the SourceError hierarchy: FetchError, CacheMiss, RetriesExhausted, HTTPRefused, CacheError); the proceedings Fetcher and OpenReviewClient (POLICY + login) subclass HttpClient. common.py: Report base (fetched → crawl_window), sources_manifest, write_marker/read_markers, Crawls (the one replay), CrawlError (= MinerError). crawl.replay_all replays v2, v1, NeurIPS, PMLR; snapshot.load_sources and cli.main catch SourceError once.
Deliberate behaviour changes (none reach a snapshot): proceedings no longer follow redirects (3xx → HTTPRefused); a body over the cap is refused at once for every source (OpenReview used to retry); a corrupt OpenReview cache entry is CacheError, not a silent refetch; OpenReview 5xx honour Retry-After; refusal reason http_<status> (was http_refused); proceedings retry log event crawl_retry_wait (was crawl_fetch_backoff); an OpenReview cache miss logs cli_refused at ERROR like every FetchError.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
One HTTP layer (sources/http.py: Transport/Request/Response/Clock, no-redirect bounded urllib transport, one host allowlist and canonical URL, one Policy-driven pacing/retry/backoff with Retry-After and ratelimit-reset seconds, one atomic ResponseCache whose per-source codec keeps both on-disk layouts, one SourceError hierarchy) under the proceedings Fetcher and OpenReviewClient (login on top); common.py gives one Report (crawl_window), one marker writer/reader and one replay (Crawls) used by crawl.replay_all for v2, v1, NeurIPS and PMLR; cli.main and snapshot.load_sources catch SourceError once. Verified: combined v2+v1+NeurIPS+PMLR snapshot byte-identical to the pre-refactor baseline (test_combined_snapshot.py); a cache written by the old code replays to the same hashes; fixture tests unchanged but for imports; test_http.py covers allowlist, off-host answers, body cap and errors for all sources; uv run pytest 4041 passed, make lint and make tooling green.
<!-- SECTION:FINAL_SUMMARY:END -->
