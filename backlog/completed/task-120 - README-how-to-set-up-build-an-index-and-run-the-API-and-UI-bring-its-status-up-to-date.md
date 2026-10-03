---
id: TASK-120
title: >-
  README: how to set up, build an index and run the API and UI; bring its status
  up to date
status: Done
assignee:
  - '@jeevanp03'
created_date: '2026-09-29 15:01'
updated_date: '2026-09-29 15:06'
labels:
  - docs
milestone: m-4
dependencies: []
priority: high
ordinal: 113000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
README.md has no setup or run instructions (only a pointer to CONTRIBUTING.md) and its status line is stale: it says the UI pages are placeholders (M3b built them, TASK-041..045) and does not mention the M4 crawlers or op eval coverage. The task-hygiene rule keeps docs as-built, but no recent diff touched README, so docs-reviewer never saw it drift.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 README has a quickstart: prerequisites, setup, getting data (crawl or RIS), snapshot and index build, making an index current, running op serve and the UI (dev and production), each command verified by running it
- [x] #2 task-hygiene names README.md's status and quickstart as things every milestone PR re-checks, so they can't drift silently again
- [x] #3 README's status line matches what is built (M3 UI, M4 crawlers and coverage report), links the specs and CONTRIBUTING.md, and says production deployment (deploy/, TASK-065) is planned for M6
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Every Quickstart command was run on 2026-09-29 against the M2 index (a7cfd04b656f): op serve with --cors-origin (healthz, search, CORS allowed only for the UI origin), the dev UI (/, /search, /coverage, /help/syntax all 200), the production build and start (API URL compiled into the bundle), and serving via a relative current symlink in a scratch data dir.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
README.md now has a verified Quickstart (prerequisites, setup, crawling or RIS import, snapshot and index build, making an index current, CLI search and export, op serve with CORS, the UI in dev and production, op eval coverage, tests) and an as-built Status table (M1 to M4; M5 and M6 planned). docs-reviewer checks README's Status and Quickstart on every diff, and task-hygiene says which changes must update it. CLAUDE.md's Makefile targets and a CONTRIBUTING link to the Quickstart fixed.
<!-- SECTION:FINAL_SUMMARY:END -->
