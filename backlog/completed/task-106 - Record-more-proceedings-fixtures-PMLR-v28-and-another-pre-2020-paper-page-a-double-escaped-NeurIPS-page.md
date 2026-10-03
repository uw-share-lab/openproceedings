---
id: TASK-106
title: >-
  Record more proceedings fixtures: PMLR v28 and another pre-2020 paper page, a
  double-escaped NeurIPS page
status: Done
assignee:
  - '@codex'
created_date: '2026-09-27 21:34'
updated_date: '2026-09-28 01:07'
labels:
  - ingest
  - testing
milestone: m-4
dependencies: []
ordinal: 103000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-052/053's golden cases for these are derived from existing fixtures rather than recorded; record real ones.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Fixtures recorded and scrubbed,Tests read them in place of the derived cases
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Record and scrub a real pre-2020 PMLR paper page, PMLR v202/v267 indexes, and a real double-escaped NeurIPS page. 2. Replace derived golden cases with those fixtures under failing tests. 3. Run focused and full verification.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
From TASK-105: also record the v202 and v267 index pages to confirm which PMLR volumes carry the OpenReview forum link (only v235 is recorded).

Recorded and scrubbed the real PMLR v28 paper page, v202/v267 indexes, NeurIPS 2025 double-escaped author case, and the NeurIPS 2025 companion listing. Tests now read the fixtures directly, including explicit v28 page extraction and v202/v267 forum-link assertions.

Validation: make lint passed; focused post-review suite 473 passed; full make test passed (4119 backend, 2 opt-in skips, 304 frontend); make tooling passed; independent review found no remaining findings.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Replaced derived proceedings cases with recorded scrubbed fixtures for pre-OpenReview PMLR extraction, later PMLR forum links and NeurIPS double escaping. Full gates and review passed.
<!-- SECTION:FINAL_SUMMARY:END -->
