---
id: TASK-102
title: Expiry for the OpenReview raw-response cache
status: Done
assignee: []
created_date: '2026-09-27 21:19'
updated_date: '2026-09-27 23:56'
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
- [x] #1 TTL per listing type documented in spec 01,Expired entries are re-fetched and the refetch is logged,Tests with a fake clock
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Expiry lives in the unified cache: Policy.ttl(url, now) -> seconds | None (http.py; default never_expires). HttpClient.through_cache re-fetches a hit past its TTL on a live client, overwrites it, counts stats.expired and logs <prefix>_cache_expired (url, age_s, ttl_s); a client without a transport (--offline, --dry-run, snapshot build) never expires, so replay stays reproducible (test_combined_snapshot hashes unchanged; the full suite also passes with the system clock moved to 2031). Codec gained fetched_at(entry). OpenReview: openreview_client.ttl/listing_kind/TTL - API v2 accepted listing 7 d while its venue-year is open (year >= this calendar year), 365 d after; submission/rejected/withdrawn/desk-rejected listings and groups 1 d, then 90 d; a request naming no venue-year 1 d; API v1 never. Proceedings never expire (--refresh for a newly published year). openreview_v2._pages re-fetches the rest of a listing once one page expired, so its pages agree. Table in spec 01 Pipeline step 1 (Cache expiry); openreview-api and snapshots skills updated. Tests: backend/tests/unit/ingest/test_cache_expiry.py (fake clock).
<!-- SECTION:FINAL_SUMMARY:END -->
