---
id: TASK-050
title: OpenReview API v2 crawler
status: To Do
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-09-27 20:42'
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
- [ ] #1 Authenticated from .env; honours 429 Retry-After; resumable; cached
- [ ] #2 Only content.venueid on the submission note decides track/status
- [ ] #3 Recorded fixtures per year; --offline replays the cache
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reuse scholarmend (PyPI, pinned) for the OpenReview client pieces: login, OpenReviewResolver, cache and claim ledger, instead of re-implementing them. Check its API at the pinned version first.

TASK-002 facts (docs/research/2026-09-27-openreview-and-proceedings-facts.md; openreview-api skill): anonymous requests get HTTP 200 + HTML challenge (treat non-JSON as auth failure); limit <= 1000; count only with offset; select= works; notes 500/h, groups 700/h, use ratelimit-reset (seconds), not x-ratelimit-reset (epoch). Env names OPENREVIEW_USERNAME/OPENREVIEW_PASSWORD. Each v2 group names its four venueids and public_* flags. Fixtures: backend/tests/fixtures/http/openreview/v2/.
<!-- SECTION:NOTES:END -->
