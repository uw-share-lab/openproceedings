---
id: TASK-161
title: >-
  Merge queue for dev: replace require-up-to-date with a queue that keeps the
  review gate
status: In Progress
assignee: []
created_date: '2026-10-02 04:55'
updated_date: '2026-10-02 04:55'
labels:
  - tooling
  - ci
dependencies: []
priority: high
ordinal: 136000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The dev branch protection requires a PR to be up to date with dev (strict required checks), and the review gate (review-attested) is keyed to the exact head sha. Every merge into dev therefore forces each other open PR to rebase, re-record its review (patch-id comparison, remapped dispositions) and re-attest, all by hand, one PR at a time. A GitHub merge queue on dev removes the rebase: a PR is added to the queue (gh pr merge N --merge --auto), GitHub builds a temporary gh-readonly-queue/dev/pr-N-<sha> branch of dev plus the queued PRs, runs the required checks on it under the merge_group event, and merges it when they pass. The gates in pr-gates.yml read github.event.pull_request, which is absent in merge_group, so they must be taught that event without becoming no-ops: each PR in the group must still carry an APPROVE attestation for its own head, a learnings entry (or the no-learning label), and no AI attribution. Repo settings are not changed here; the lead applies the ruleset commands after the PR merges (owner approved).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 lint, test, claude-tooling and pr-gates run on merge_group, so the queue's builds report all six required checks under their existing names
- [ ] #2 test.yml takes its OpenAPI baseline from merge_group.base_sha in a merge_group run
- [ ] #3 In merge_group, review-attested resolves every PR in the group from the queue commits (base_sha..head_sha first-parent merges, cross-checked with the head_ref gh-readonly-queue/dev/pr-N-<sha>) and passes only when each PR is open, targets dev, has that commit as its head and its current body attests APPROVE for it; anything it cannot resolve fails closed
- [ ] #4 In merge_group, learnings checks each PR's own diff (merge-base of its parents) for an added or extended entry unless that PR carries no-learning, and attribution scans every commit in the group plus each PR's title and body; both fail closed
- [ ] #5 The merge_group logic lives in a script with a case table under .claude/scripts/tests/ and mutants in .claude/scripts/mutants/ that the table kills
- [ ] #6 decision-030 records the design, the trust model and the fallback
- [ ] #7 Spec 08 (CI, Branch protection), pr-workflow, review-gates, ci-engineer and CONTRIBUTING describe the queue flow: add the PR to the queue instead of rebasing
- [ ] #8 The PR body and task notes carry the exact gh api commands that enable the queue on dev and drop strict up-to-date; the lead applies them after merge
<!-- AC:END -->
