---
id: TASK-212
title: >-
  Fail make tooling when frontend/package.json and the lock's workspace entry
  disagree
status: In Progress
assignee:
  - '@jeevanp03'
created_date: '2026-10-08 03:31'
labels:
  - tooling
  - ci
dependencies: []
ordinal: 146000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Dependabot's npm updater can write a caret into package-lock.json's packages["frontend"] entry while frontend/package.json pins the version exactly (PR #124: eslint-config-next ^16.3.8; PR #100: Vitest). npm ci accepts it, so nothing failed. /dependabot-review's npm_lock.py catches it, but only inside the weekly routine. Owner decision 2026-10-07: check it in make tooling, so CI claude-tooling catches it on every PR.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A make tooling check fails when any dependencies, devDependencies, optionalDependencies or peerDependencies spec in package.json or frontend/package.json differs from the lock's packages[""] / packages["frontend"] entry (a range vs an exact pin, a missing or an extra entry) and passes when they agree
- [ ] #2 npm_lock.py uses the same comparison (one shared function, no duplicate)
- [ ] #3 Case-table rows in make tooling cover each section, pins vs ranges, missing and extra entries, the root entry, and malformed input; mutants for the new check are killed
- [ ] #4 The check passes on dev and fails on PR #124's Dependabot commit 34059c0f
- [ ] #5 Spec 08 and /dependabot-review step 3 describe the check
<!-- AC:END -->
