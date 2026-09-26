---
id: TASK-008
title: 'M0 exit: CI green on dev and roster checks pass'
status: Done
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-09-26 01:07'
labels:
  - ops
milestone: m-0
dependencies: []
ordinal: 7000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Close M0 once the tooling PR has merged and every required check is green on dev.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 All six required checks (lint, test, claude-tooling, attribution, learnings, review-attested) green on the merged tooling PR
- [x] #2 make lint and make tooling pass on a fresh clone of dev after scripts/setup-dev.sh and uv sync
- [x] #3 Branch protection on dev and main verified via gh api (checks, admins, main approval)
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
PR #1 merged into dev (1377b9d) with all six required checks green. A fresh clone of dev passes make lint and make tooling (406 rows, roster lint 0 errors) after scripts/setup-dev.sh. Branch protection verified via gh api: dev and main require the six checks with admins enforced; main requires 1 approval.
<!-- SECTION:FINAL_SUMMARY:END -->
