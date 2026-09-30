---
id: TASK-067
title: Pre-release security review
status: In Progress
assignee:
  - '@jeevan'
created_date: '2026-09-26 01:06'
updated_date: '2026-09-30 23:07'
labels:
  - ops
  - security
milestone: m-6
dependencies:
  - TASK-065
ordinal: 66000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Full-tree security-reviewer pass before going public with an instance.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 No open Must/Should findings
- [ ] #2 Rate limits and CORS verified on the deployed instance
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Full-tree security-reviewer pass in five parallel scopes: API and search; ingest and crawlers; takedown tooling (TASK-136); hooks, scripts, githooks and Makefile; CI, deploy, dependencies and frontend.
2. Fix every Must and Should with tests (TDD). Defer only what needs code or a decision that doesn't exist yet.
3. Closing: make lint, make tooling, one full make test, learnings, /review-gate, PR into dev.
4. AC#2 (rate limits and CORS verified on the deployed instance) waits on TASK-065, which waits on TASK-064 (hosting).
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-09-30 review (5 security-reviewer passes, whole tree). Musts: (1) query/normalize.py tokenizer quadratic on runs of combining marks (anonymous CPU DoS via q, or stored in an abstract) - fixed, linear; (2) an older index version served a listed paper's abstract under a pre-rekey id or a merged-away duplicate id, and op takedown check missed it - fixed (takedowns.same_paper, API + op export + check title sweep); (3) protect-data-dir.sh let forced whole-tree git adds stage data/ - fixed in this branch (it was a queued follow-up, not yet filed). Shoulds fixed: pinned-open slot queued without bound (503 API_BUSY after pinned_open_wait_seconds; op serve --pinned-indexes); a missing takedown list failed open (required off loopback, or once any snapshot withheld; build and check refuse too); the check ignored ids the log withholds that the list dropped; the OpenReview token could be echoed via a ValueError; 11 hook evasions (xargs, git -c/aliases, heads/dev, local commits on main, record-review base, forged op-reviews records, $(cat file) attribution, backlog path normalisation, APFS case folding, rm -rf above data/, unlink); Dependabot missing npm; no HSTS. Known follow-ups confirmed and left to their tasks: TASK-148 (CI builds web.Dockerfile), TASK-149 (digest pins), TASK-150 (tantivy Dependabot); api container mounts and user: TASK-065. AC#2 stays open: it needs the deployed instance (TASK-065, which waits on TASK-064).
<!-- SECTION:NOTES:END -->
