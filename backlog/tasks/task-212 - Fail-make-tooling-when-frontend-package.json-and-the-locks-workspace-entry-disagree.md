---
id: TASK-212
title: >-
  Fail make tooling when frontend/package.json and the lock's workspace entry
  disagree
status: Done
assignee:
  - '@jeevanp03'
created_date: '2026-10-08 03:31'
updated_date: '2026-10-08 05:27'
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
- [x] #1 A make tooling check fails when any dependencies, devDependencies, optionalDependencies or peerDependencies spec in package.json or frontend/package.json differs from the lock's packages[""] / packages["frontend"] entry (a range vs an exact pin, a missing or an extra entry) and passes when they agree
- [x] #2 npm_lock.py uses the same comparison (one shared function, no duplicate)
- [x] #3 Case-table rows in make tooling cover each section, pins vs ranges, missing and extra entries, the root entry, and malformed input; mutants for the new check are killed
- [x] #4 The check passes on dev and fails on PR #124's Dependabot commit 34059c0f
- [x] #5 Spec 08 and /dependabot-review step 3 describe the check
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Move the manifest/lock comparison from npm_lock.py into .claude/scripts/dependabot/npm_specs.py (mismatches(), stdlib, typed); npm_lock.py imports it. 2. npm_specs.py reads package.json, frontend/package.json and package-lock.json in its checkout (or --root) and exits 1 naming each mismatch. 3. make tooling runs it; rows in test-tooling-scripts.sh; mutants in mutants/dependabot.json. 4. Spec 08, /dependabot-review step 3, README, pr-workflow skill, ci-engineer. 5. Verify: dev passes, 34059c0f (PR 124) and 1e73d7d0 (PR 100) fail.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Verified: npm_specs.py passes on this branch (dev 3aa36eb1 plus the change). With --root on a checkout of PR 124's Dependabot commit 34059c0f it exits 1: frontend/package.json devDependencies.eslint-config-next is '16.3.8', the lock's packages[frontend] has '^16.3.8'. On PR 100's Dependabot commit 1e73d7d0 it exits 1: devDependencies.vitest '5.0.3' vs '^5.0.3'.

Focused review (round 1): 1 Should (the two --root rows accepted any non-zero exit) and 3 Nits (malformed section reported as a FIX by npm_lock.py; WORKSPACES hard-coded with no check of the root workspaces list; an empty non-object lock section with no manifest passed); all fixed in 9d9bdf81. Mutants: the 20 new or moved ones (npm_specs.py, the two moved npm_lock comparisons, the malformed-section PROBLEM) all killed in a scratch loop against test-tooling-scripts.sh and test-dependabot.sh.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
make tooling (and so CI claude-tooling) now runs .claude/scripts/dependabot/npm_specs.py: every spec in dependencies, devDependencies, optionalDependencies and peerDependencies of package.json and frontend/package.json must be written exactly as package-lock.json's packages[""] and packages["frontend"] hold it, none missing and none extra; a missing or malformed file, section or entry, an unknown workspace, or a --root that isn't a directory fails too. npm_lock.py imports the same mismatches() (malformed sections are now a PROBLEM there, not a FIX). It passes on dev and fails on PR 124's Dependabot commit 34059c0f (eslint-config-next ^16.3.8) and PR 100's 1e73d7d0 (vitest ^5.0.3). /dependabot-review step 3 runs it with --root . (the routine runs dev's copy). Rows in test-tooling-scripts.sh and dependabot_cases.py, 18 new mutants. Spec 08, README, pr-workflow skill, ci-engineer and the learnings entry updated.
<!-- SECTION:FINAL_SUMMARY:END -->
