---
id: TASK-173
title: >-
  enforce-pr-workflow: hint at absolute paths when a cd-then-commit is refused
  on a protected branch (TASK-156 follow-up)
status: In Progress
assignee:
  - '@jeevanparmar'
created_date: '2026-10-02 10:33'
updated_date: '2026-10-02 20:49'
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
- [ ] #3 `make tooling` and `python3 .claude/scripts/mutate.py --changed` pass
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Preserve recovered implementation; reproduce regressions, scan sed script files, add deterministic join and case-folding coverage, run lint/tooling/changed mutation checks, update docs and learnings, complete tasks and commit for independent review.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Recovered protected-cd verdict and absolute git-C hint verified by make tooling; changed mutation verification pending.
<!-- SECTION:NOTES:END -->
