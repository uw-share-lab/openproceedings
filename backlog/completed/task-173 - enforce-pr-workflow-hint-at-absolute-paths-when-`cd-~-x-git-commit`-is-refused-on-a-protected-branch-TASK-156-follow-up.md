---
id: TASK-173
title: >-
  enforce-pr-workflow: hint at absolute paths when a cd-then-commit is refused
  on a protected branch (TASK-156 follow-up)
status: Done
assignee:
  - '@jeevanparmar'
created_date: '2026-10-02 10:33'
updated_date: '2026-10-03 08:06'
labels:
  - tooling
  - ux
  - deferred
dependencies: []
references:
  - .claude/hooks/enforce-pr-workflow.sh
priority: low
ordinal: 143000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Source: TASK-156 review (PR #83, 2026-10-02), deferred. Run from a checkout on a protected branch, `cd ~/x && git commit …` gets the "protected branch" refusal even when the commit would land in the feature worktree at ~/x, because the hook can't resolve the target the way the shell would. The refusal is the safe outcome, but the message sends the agent the wrong way. Add a hint to the message: run the command with absolute paths (`git -C /abs/path commit …`).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 When the refused commit's directory came from a `cd` the hook couldn't resolve to the protected checkout, the message adds a hint to use absolute paths (`git -C <abs path>`)
- [x] #2 A case-table row checks the hint text; no row's block/allow verdict changes
- [x] #3 `make tooling` and `python3 .claude/scripts/mutate.py --changed` pass
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Preserve recovered implementation; reproduce regressions, scan sed script files, add deterministic join and case-folding coverage, run lint/tooling/changed mutation checks, update docs and learnings, complete tasks and commit for independent review.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Recovered protected-cd verdict and absolute git-C hint verified by make tooling; changed mutation verification pending.

Complete official make mutate-changed on reviewed source 9d035a1877e806e8ea11b5c9fde7ca3cc557812a: 417 mutants: 0 problem(s), exit 0; 413 killed and four independently audited equivalent survivors, no stale patterns. Raw /tmp/hooks-official-linux-9d.log, exact .head, .exit contains 0; post-run host/container tracked-byte hashes unchanged. Fresh Node22 make lint and make tooling both passed exit 0 (/tmp/hooks-lint-9d.log and /tmp/hooks-tooling-9d.log). Interrupted earlier runs remain diagnostic only. Final metadata commit gates and exact-head review follow.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Protected-branch refusal after unresolved cd includes an absolute git -C path hint while preserving verdicts. Hint and verdict controls, complete official 417-mutant validation and make tooling passed exit 0.
<!-- SECTION:FINAL_SUMMARY:END -->
