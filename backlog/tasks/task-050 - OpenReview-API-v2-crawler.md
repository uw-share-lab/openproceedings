---
id: TASK-050
title: OpenReview API v2 crawler
status: In Progress
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-09-27 21:19'
labels:
  - ingest
milestone: m-4
dependencies:
  - TASK-002
  - TASK-022
  - TASK-048
  - TASK-049
ordinal: 49000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
ICLR 2024+, NeurIPS 2023+, ICML 2023+ (openreview-api skill).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Authenticated from .env; honours 429 Retry-After; resumable; cached
- [x] #2 Only content.venueid on the submission note decides track/status
- [ ] #3 Recorded fixtures per year; --offline replays the cache
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reuse scholarmend (PyPI, pinned) for the OpenReview client pieces: login, OpenReviewResolver, cache and claim ledger, instead of re-implementing them. Check its API at the pinned version first.

TASK-002 facts (docs/research/2026-09-27-openreview-and-proceedings-facts.md; openreview-api skill): anonymous requests get HTTP 200 + HTML challenge (treat non-JSON as auth failure); limit <= 1000; count only with offset; select= works; notes 500/h, groups 700/h, use ratelimit-reset (seconds), not x-ratelimit-reset (epoch). Env names OPENREVIEW_USERNAME/OPENREVIEW_PASSWORD. Each v2 group names its four venueids and public_* flags. Fixtures: backend/tests/fixtures/http/openreview/v2/.

As built (t050, on feat/m4-crawlers): ingest/sources/openreview_client.py (OpenReviewClient: lazy login via its own transport from OPENREVIEW_USERNAME/PASSWORD in the environment or .env; 401 or a 200 HTML page -> one fresh login, then OpenReviewAuthError; no redirects; host allowlist; pacing 1 s; budget wait on ratelimit-remaining 0 using ratelimit-reset seconds, never x-ratelimit-reset; 429 -> Retry-After (seconds or HTTP date) -> ratelimit-reset -> backoff; 5xx/network/truncated JSON -> exponential backoff with jitter; bounded attempts; waits capped at 3,701 s; scholarmend Cache under data/cache/openreview/v2/http keyed by the canonical URL). ingest/sources/openreview_v2.py (group tree via ?parent= with Workshop/Workshop_<City>/Track expanded, proposal and non-v2 groups skipped and reported; every venue's accepted + submission/rejected/withdrawn/desk-rejected venueids per decision-012; limit 1000, offset, sort number:asc, stop on a short page, count == rows == distinct ids else refused, ignored-offset guard; only the submission note (id == forum) and its own content.venueid through classify_venueid decide track/status; claims source openreview_v2 with the page URL and cached fetched_at). op ingest openreview --venue V --years YYYY[-YYYY] [--offline | --dry-run | --refresh]; a finished crawl writes cache/openreview/v2/crawls/<Venue>-<Year>.json and op snapshot build replays it offline (manifest sources.openreview_v2 with its crawl_window). Deviation from the implementation note: scholarmend's login is not reused (it bypasses the injectable transport, follows redirects and reads the challenge page as a JSONDecodeError); its Cache is. Tests: test_openreview_client.py (23) and test_openreview_v2.py (38), recorded fixtures only. AC #3 not yet met: --offline replay works, but recorded fixtures exist only for ICLR 2024-2025, NeurIPS 2023-2025, ICML 2024-2025 (none for ICML 2023, ICLR/NeurIPS/ICML 2026) and no ?parent= group listing is recorded; recording needs live credentials (not configured). No live crawl was run.

AC#3 open: needs fixtures recorded with live credentials (ICML 2023, the 2026 venue-years, one ?parent= group listing per venue). Group discovery via ?parent= is unverified until then.
<!-- SECTION:NOTES:END -->
