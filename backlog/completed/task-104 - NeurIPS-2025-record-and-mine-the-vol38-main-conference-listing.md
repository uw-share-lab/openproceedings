---
id: TASK-104
title: 'NeurIPS 2025: record and mine the vol38-main-conference listing'
status: Done
assignee:
  - '@codex'
created_date: '2026-09-27 21:34'
updated_date: '2026-09-28 01:07'
labels:
  - ingest
milestone: m-4
dependencies: []
ordinal: 101000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The 2025 year page links /paper_files/paper/2025/vol38-main-conference; the miner reports it as see_also with a warning but doesn't crawl it because its structure isn't recorded.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The page is recorded as a fixture,The miner mines it as a listing with its track rules,The see_also warning goes away for 2025
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Record and scrub the public NeurIPS 2025 vol38 main-conference page. 2. Add a failing test that requires the year miner to follow and mine that listing with main-track classification. 3. Implement the minimal listing-follow behavior, update docs, and verify.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Recorded and scrubbed the NeurIPS 2025 vol38-main-conference page. The year miner now follows the explicit base/companion pair, mines main, datasets_benchmarks and position alongside Creative AI, and reserves see_also/warnings for unknown links.

Validation: make lint passed; focused post-review suite 473 passed; full make test passed (4119 backend, 2 opt-in skips, 304 frontend); make tooling passed; independent review found no remaining findings.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Recorded and mined the NeurIPS 2025 main-conference companion listing with correct track rules and no warning for the known followed link; retained warnings for unknown cross-links. Full gates and review passed.
<!-- SECTION:FINAL_SUMMARY:END -->
