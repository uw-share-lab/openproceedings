---
id: TASK-050
title: OpenReview API v2 crawler
status: Done
assignee:
  - '@codex'
created_date: '2026-09-26 01:06'
updated_date: '2026-09-29 03:44'
labels:
  - ingest
milestone: m-4
dependencies:
  - TASK-002
  - TASK-022
  - TASK-048
  - TASK-049
modified_files:
  - backend/tests/fixtures/http/scrub.py
  - backend/tests/fixtures/http/openreview/v2/icml-2023/groups-parent.json
  - backend/tests/fixtures/http/openreview/v2/icml-2023/notes-accepted.json
  - backend/tests/fixtures/http/openreview/v2/iclr-2026/groups-parent.json
  - backend/tests/fixtures/http/openreview/v2/iclr-2026/notes-accepted.json
  - backend/tests/fixtures/http/openreview/v2/neurips-2026/groups-parent.json
  - backend/tests/fixtures/http/openreview/v2/neurips-2026/notes-accepted.json
  - backend/tests/fixtures/http/openreview/v2/icml-2026/groups-parent.json
  - backend/tests/fixtures/http/openreview/v2/icml-2026/notes-accepted.json
  - backend/tests/unit/ingest/test_openreview_v2.py
  - backend/tests/unit/ingest/test_venueid.py
  - docs/research/2026-09-27-openreview-and-proceedings-facts.md
  - .claude/skills/openreview-api/SKILL.md
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
- [x] #3 Recorded fixtures per year; --offline replays the cache
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Add a failing inventory test that requires one recorded note for every API v2 venue-year and a recorded `?parent=` group listing for each venue.
2. Record the missing ICML 2023 and ICLR/NeurIPS/ICML 2026 public projections through `OpenReviewClient` using credentials from the main checkout `.env`, then scrub all free text before committing.
3. Exercise each new fixture through the real cache codec and an offline client, while retaining the existing end-to-end crawl replay test.
4. Scan fixtures for credentials/personal data, update the OpenReview research/skill documentation and TASK-050 notes, then run targeted, ingest, lint and tooling gates.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reuse scholarmend (PyPI, pinned) for the OpenReview client pieces: login, OpenReviewResolver, cache and claim ledger, instead of re-implementing them. Check its API at the pinned version first.

TASK-002 facts (docs/research/2026-09-27-openreview-and-proceedings-facts.md; openreview-api skill): anonymous requests get HTTP 200 + HTML challenge (treat non-JSON as auth failure); limit <= 1000; count only with offset; select= works; notes 500/h, groups 700/h, use ratelimit-reset (seconds), not x-ratelimit-reset (epoch). Env names OPENREVIEW_USERNAME/OPENREVIEW_PASSWORD. Each v2 group names its four venueids and public_* flags. Fixtures: backend/tests/fixtures/http/openreview/v2/.

As built (t050, on feat/m4-crawlers): ingest/sources/openreview_client.py (OpenReviewClient: lazy login via its own transport from OPENREVIEW_USERNAME/PASSWORD in the environment or .env; 401 or a 200 HTML page -> one fresh login, then OpenReviewAuthError; no redirects; host allowlist; pacing 1 s; budget wait on ratelimit-remaining 0 using ratelimit-reset seconds, never x-ratelimit-reset; 429 -> Retry-After (seconds or HTTP date) -> ratelimit-reset -> backoff; 5xx/network/truncated JSON -> exponential backoff with jitter; bounded attempts; waits capped at 3,701 s; scholarmend Cache under data/cache/openreview/v2/http keyed by the canonical URL). ingest/sources/openreview_v2.py (group tree via ?parent= with Workshop/Workshop_<City>/Track expanded, proposal and non-v2 groups skipped and reported; every venue's accepted + submission/rejected/withdrawn/desk-rejected venueids per decision-012; limit 1000, offset, sort number:asc, stop on a short page, count == rows == distinct ids else refused, ignored-offset guard; only the submission note (id == forum) and its own content.venueid through classify_venueid decide track/status; claims source openreview_v2 with the page URL and cached fetched_at). op ingest openreview --venue V --years YYYY[-YYYY] [--offline | --dry-run | --refresh]; a finished crawl writes cache/openreview/v2/crawls/<Venue>-<Year>.json and op snapshot build replays it offline (manifest sources.openreview_v2 with its crawl_window). Deviation from the implementation note: scholarmend's login is not reused (it bypasses the injectable transport, follows redirects and reads the challenge page as a JSONDecodeError); its Cache is. Tests: test_openreview_client.py (23) and test_openreview_v2.py (38), recorded fixtures only. AC #3 not yet met: --offline replay works, but recorded fixtures exist only for ICLR 2024-2025, NeurIPS 2023-2025, ICML 2024-2025 (none for ICML 2023, ICLR/NeurIPS/ICML 2026) and no ?parent= group listing is recorded; recording needs live credentials (not configured). No live crawl was run.

AC#3 open: needs fixtures recorded with live credentials (ICML 2023, the 2026 venue-years, one ?parent= group listing per venue). Group discovery via ?parent= is unverified until then.

2026-09-29 live completion: recorded and scrubbed eight public API v2 exchanges covering ICML 2023 plus ICLR/NeurIPS/ICML 2026 (one root parent-group listing and one nonempty note listing each). Parent-group counts: 2, 4, 10, 4; representative note-list counts: 1,828, 5,351, 95 Creative AI, 6,341. Every capture passed the client public projection before recording; credential/auth/email/profile scans are clean. New tests require every supported v2 venue-year, validate exact parent roots, feed each exchange through the real cache codec, and replay with an offline no-credentials client. Targeted classifier/crawler tests: 261 passed; full ingest plus scrubber: 893 passed.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Completed the OpenReview API v2 crawler evidence set. Added authenticated, scrubbed parent-group and representative note fixtures for ICML 2023 and ICLR/NeurIPS/ICML 2026; enforced per-year fixture coverage and replayed every new exchange through the real cache with an offline, credential-free client. Updated the live research record and OpenReview skill. Privacy scans found no credentials, auth material, real email-shaped values or real profile ids. Verification: 261 focused crawler/classifier tests, 893 ingest/scrubber tests, 5,117 full backend tests (2 expected opt-in skips), 2,582 frontend tests, make lint and make tooling all passed.
<!-- SECTION:FINAL_SUMMARY:END -->
