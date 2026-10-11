---
id: TASK-237
title: >-
  Green nightly: CPU-growth timing checks, a bounded mutation runner, 12
  differential shards, a clean click-property strategy
status: Done
assignee: []
created_date: '2026-10-11 17:29'
updated_date: '2026-10-11 20:06'
labels:
  - ci
  - tests
dependencies: []
ordinal: 166000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Release readiness for v0.3.0 (spec 08 §Release step 1): no scheduled nightly passed after 2026-10-07. Root causes: wall-clock bounds at one size in linear-time tests (CI runner load), mutation shards past their limit (every mutant ran all 13 tables), the differential's group-count property past 110 min on a slow runner, and the click property's strategy gluing two $ words. See .claude/learnings/2026-10-11-a-nightly-that-gates-nothing-fails-silently.md.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A nightly run on the release candidate passes every job
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
The release candidate's nightly (run 38162202807 on dev b454f9b3, after PR #137) passed every job: CPU-growth timing checks, the bounded mutation runner and 12 differential shards.
<!-- SECTION:FINAL_SUMMARY:END -->
