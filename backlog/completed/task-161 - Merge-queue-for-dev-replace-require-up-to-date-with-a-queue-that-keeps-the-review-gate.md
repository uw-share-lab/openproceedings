---
id: TASK-161
title: >-
  Merge queue for dev: replace require-up-to-date with a queue that keeps the
  review gate
status: Done
assignee: []
created_date: '2026-10-02 04:55'
updated_date: '2026-10-02 05:17'
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
- [x] #1 lint, test, claude-tooling and pr-gates run on merge_group, so the queue's builds report all six required checks under their existing names
- [x] #2 test.yml takes its OpenAPI baseline from merge_group.base_sha in a merge_group run
- [x] #3 In merge_group, review-attested resolves every PR in the group from the queue commits (base_sha..head_sha first-parent merges, cross-checked with the head_ref gh-readonly-queue/dev/pr-N-<sha>) and passes only when each PR is open, targets dev, has that commit as its head and its current body attests APPROVE for it; anything it cannot resolve fails closed
- [x] #4 In merge_group, learnings checks each PR's own diff (merge-base of its parents) for an added or extended entry unless that PR carries no-learning, and attribution scans every commit in the group plus each PR's title and body; both fail closed
- [x] #5 The merge_group logic lives in a script with a case table under .claude/scripts/tests/ and mutants in .claude/scripts/mutants/ that the table kills
- [x] #6 Spec 08 (CI, Branch protection), pr-workflow, review-gates, ci-engineer and CONTRIBUTING describe the queue flow: add the PR to the queue instead of rebasing
- [x] #7 The PR body and task notes carry the exact gh api commands that enable the queue on dev and drop strict up-to-date; the lead applies them after merge
- [x] #8 A decision record (decision-027 on this branch; the lead asked for 030, so renumber if needed on merge) records the design, the trust model, the settings commands and the rollback
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Design: decision-027 ("Merge queue for dev: queue builds re-run the required checks and pr-gates checks every queued PR ..."). In merge_group the three pr-gates jobs run .claude/scripts/merge_group_gate.py, which walks base_sha..head_sha along first parents (one two-parent merge per queued PR; parent 2 = the PR head), names each PR from GitHub's merge subject or the one open dev PR headed at parent 2, cross-checks the newest against the head ref pr-N, and runs the PR-level check on every PR (body read from the API). Fails closed.

Settings, applied by the lead after the PR merges (owner approved), ruleset first:

gh api -X POST repos/uw-share-lab/openproceedings/rulesets --input - <<'JSON'
{"name": "dev: merge queue", "target": "branch", "enforcement": "active",
 "conditions": {"ref_name": {"include": ["refs/heads/dev"], "exclude": []}},
 "rules": [{"type": "merge_queue", "parameters": {"merge_method": "MERGE", "grouping_strategy": "ALLGREEN",
   "max_entries_to_build": 5, "min_entries_to_merge": 1, "max_entries_to_merge": 5,
   "min_entries_to_merge_wait_minutes": 0, "check_response_timeout_minutes": 60}}]}
JSON
gh api -X PATCH repos/uw-share-lab/openproceedings/branches/dev/protection/required_status_checks -F strict=false
gh api repos/uw-share-lab/openproceedings/rules/branches/dev --jq '.[].type'   # merge_queue
gh api repos/uw-share-lab/openproceedings/branches/dev/protection/required_status_checks --jq '.strict, .contexts'

Rollback: set strict=true again, then DELETE repos/uw-share-lab/openproceedings/rulesets/<id of "dev: merge queue">.
The first PR queued after the ruleset is applied is the live check of the queue's commit shape.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
lint, test, claude-tooling and pr-gates now run on merge_group. In a queue build the three pr-gates jobs run .claude/scripts/merge_group_gate.py: it resolves every queued PR from the queue's two-parent merges and checks each one's attested body, learnings entry and attribution through the API, and it fails closed. The case table test-merge-group-gate.sh (52 rows) builds real queue-shaped merges against a fake gh, and mutants/merge-group.json holds 34 mutants. Spec 08 §Merge queue and §Branch protection, pr-workflow, review-gates, ci-engineer, CONTRIBUTING and CLAUDE.md now describe queueing a PR (gh pr merge <n> --auto) instead of rebasing it. The design is decision-027. Not done in this PR: the repo settings. The lead applies the ruleset and strict=false commands in the notes and the decision after merge, and the first queued PR is the live check.
<!-- SECTION:FINAL_SUMMARY:END -->
