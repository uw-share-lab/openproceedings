---
id: TASK-097
title: Re-record the two v2 fixtures whose venue scrub.py replaced with a fake email
status: Done
assignee:
  - '@codex'
created_date: '2026-09-27 21:11'
updated_date: '2026-09-29 04:28'
labels:
  - ingest
  - testing
milestone: m-4
dependencies: []
modified_files:
  - .claude/learnings/2026-09-27-openreview-v1-venueid-is-not-status-and-anonymous-gets-html.md
  - .claude/skills/openreview-api/SKILL.md
  - backend/tests/fixtures/http/openreview/v2/iclr-2024/notes-tinypapers.json
  - >-
    backend/tests/fixtures/http/openreview/v2/neurips-2025/notes-workshop-city.json
  - backend/tests/unit/ingest/test_venueid.py
  - docs/research/2026-09-27-openreview-and-proceedings-facts.md
ordinal: 94000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
scrub.py treated the @ in venue strings such as 'Tiny Papers @ ICLR 2023' as an email address (fixed in TASK-095). The v2 fixtures for Tiny Papers 2024 and the Mexico City workshop still carry the fake-email venue. Re-record them with the fixed scrub.py once OPENREVIEW_USERNAME/PASSWORD are in .env.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Both fixtures re-recorded with their real venue strings; classifier table tests read the re-recorded venues
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Add a failing table test that reads the two affected fixtures and requires their real venue labels.
2. Fetch only the two canonical API v2 URLs with credentials from the main checkout .env, through OpenReviewClient public projection.
3. Scrub the projected captures, verify exact labels and unchanged venueid classification, scan for private/auth data, and delete all raw temporary data.
4. Update the research record, run the focused and full gates, record learnings and complete the task.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Red phase: both cases failed because content.venue was synthetic.person…@example.org. Re-recorded the world-readable public projections on 2026-09-29. Verified live labels: Tiny Papers @ ICLR 2024 Archive and ResponsibleFM @ NeurIPS 2025. The current projection also removes unused legacy top-level fields. Raw captures, cache and recorder were permanently deleted after scrubbing. Focused crawler/classifier/scrubber suite: 266 passed. Exact configured OpenReview credential values: 0 fixture matches; authorization/token scan: 0; email-shaped values: 0; nonsynthetic profile ids: 0.

Final verification: 5,119 backend tests passed with 2 expected opt-in skips; 2,582 frontend tests passed; make lint and make tooling passed.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Re-recorded the ICLR 2024 Tiny Papers and NeurIPS 2025 Mexico City workshop API v2 fixtures through the authenticated OpenReviewClient public projection and the corrected scrubber. Restored the exact public venue labels, added classifier-table regression coverage for both labels while retaining venueid as the track/status authority, updated the research inventory and OpenReview fixture guidance, and permanently deleted raw captures/cache/recorder. Privacy checks found no credentials, auth material, email-shaped values or nonsynthetic profile ids. Verification: 266 focused tests; 5,119 backend tests with 2 expected skips; 2,582 frontend tests; lint and tooling clean.
<!-- SECTION:FINAL_SUMMARY:END -->
