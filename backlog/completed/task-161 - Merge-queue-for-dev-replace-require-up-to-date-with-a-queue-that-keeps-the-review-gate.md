---
id: TASK-161
title: >-
  Merge queue for dev: replace require-up-to-date with a queue that keeps the
  review gate
status: Done
assignee: []
created_date: '2026-10-02 04:55'
updated_date: '2026-10-02 06:27'
labels:
  - tooling
  - ci
dependencies: []
priority: high
ordinal: 136000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The dev branch protection requires a PR to be up to date with dev (strict required checks), and the review gate (review-attested) is keyed to the exact head sha. Every merge into dev therefore forces each other open PR to rebase, re-record its review (patch-id comparison, remapped dispositions) and re-attest, all by hand, one PR at a time. A GitHub merge queue on dev removes the rebase: a PR is added to the queue (gh pr merge N --auto), GitHub builds a temporary gh-readonly-queue/dev/pr-N-<sha> branch of dev plus the queued PRs, runs the required checks on it under the merge_group event, and merges it when they pass. The gates in pr-gates.yml read github.event.pull_request, which is absent in merge_group, so they must be taught that event without becoming no-ops: each PR in the group must still carry an APPROVE attestation for its own head, a learnings entry (or the no-learning label), and no AI attribution. Repo settings are not changed here; the lead applies the commands after the PR merges (owner approved).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 lint, test, claude-tooling and pr-gates run on merge_group, so the queue's builds report all six required checks under their existing names
- [x] #2 test.yml takes its OpenAPI baseline from merge_group.base_sha in a merge_group run
- [x] #3 In merge_group, review-attested resolves every PR in the group from the queue commits (base_sha..head_sha first-parent merges, cross-checked with the head_ref gh-readonly-queue/dev/pr-N-<sha>) and passes only when each PR is open (or merged by this group's own queue commit), targets dev, has that commit as its head and its current body attests APPROVE for it; anything it cannot resolve fails closed
- [x] #4 In merge_group, learnings checks each PR's own diff (merge-base of its parents) for an added or extended entry unless that PR carries no-learning, and attribution scans every commit in the group plus each PR's title and body; both fail closed
- [x] #5 The merge_group logic lives in a script with a case table under .claude/scripts/tests/ (reason-checked rows plus a workflow-wiring row) and mutants in .claude/scripts/mutants/ that the table kills
- [x] #6 Spec 08 (CI, Merge queue, Git and PR rules, Branch protection, Release), pr-workflow, review-gates, ci-engineer, release-manager, CONTRIBUTING and CLAUDE.md describe the queue flow (queue the PR instead of rebasing) and the flow before the settings land
- [x] #7 The PR body and task notes carry the exact gh api commands (allow_auto_merge, the dev merge-queue ruleset, strict=false, verify; rollback in decision-027); the lead applies them after merge
- [x] #8 A decision record (decision-027 on this branch; the lead asked for 030, so renumber on merge if needed) records the design, the trust model, the settings commands and the rollback
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Design: decision-027 ("Merge queue for dev: queue builds re-run the required checks and pr-gates checks every queued PR ..."). In merge_group the three pr-gates jobs run .claude/scripts/merge_group_gate.py. It walks base_sha..head_sha along first parents (one two-parent merge per queued PR; parent 2 = the PR head), names each PR from GitHub's merge subject or the one open dev PR headed at parent 2, and checks the newest against the head ref's pr-N. It then runs the PR-level check on every PR, reading the body from the API. A PR ahead that is already merged passes only if this group's queue commit merged it. The gate fails closed.

Settings, applied by the lead after the PR merges (owner approved). Order: auto-merge, then the ruleset, then strict=false.

gh api -X PATCH repos/uw-share-lab/openproceedings -F allow_auto_merge=true
gh api -X POST repos/uw-share-lab/openproceedings/rulesets --input - <<'JSON'
{"name": "dev: merge queue", "target": "branch", "enforcement": "active",
 "conditions": {"ref_name": {"include": ["refs/heads/dev"], "exclude": []}},
 "rules": [{"type": "merge_queue", "parameters": {"merge_method": "MERGE", "grouping_strategy": "ALLGREEN",
   "max_entries_to_build": 5, "min_entries_to_merge": 1, "max_entries_to_merge": 5,
   "min_entries_to_merge_wait_minutes": 0, "check_response_timeout_minutes": 60}}]}
JSON
gh api -X PATCH repos/uw-share-lab/openproceedings/branches/dev/protection/required_status_checks -F strict=false
gh api repos/uw-share-lab/openproceedings --jq .allow_auto_merge                  # true
gh api repos/uw-share-lab/openproceedings/rules/branches/dev --jq '.[].type'       # merge_queue
gh api repos/uw-share-lab/openproceedings/branches/dev/protection/required_status_checks --jq '.strict, .contexts'

To queue a PR: gh pr merge <n> --auto (or the GraphQL enqueuePullRequest call in spec 08 §Git and PR rules).
Rollback: set strict=true again, then DELETE repos/uw-share-lab/openproceedings/rulesets/<id of "dev: merge queue">. The script with its uniqueness check is in decision-027.
The first PR queued after the ruleset is applied is the live check of the queue's commit shape. Its pr-gates log line "merge group ...: #N @ ..." shows whether base_sha is dev's tip; record that in decision-027.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
lint, test, claude-tooling and pr-gates now run on merge_group. In a queue build the three pr-gates jobs run .claude/scripts/merge_group_gate.py: it resolves every queued PR from the queue's two-parent merges and checks each one's attested body, learnings entry and attribution through the API, accepting a PR ahead only if it is open or was merged by the group's own queue commit, and it fails closed. The case table test-merge-group-gate.sh (67 rows) builds real queue-shaped merges against a fake gh and checks the reason for every refusal. Its last row checks the workflow wiring as text: the guard step, one gate step per job, no job-level skip or continue-on-error, the merge_group triggers, and one attribution pattern. mutants/merge-group.json holds 55 mutants, all killed (make mutate-changed). Spec 08 §Merge queue, §Git and PR rules, §Branch protection and §Release step 7, pr-workflow, review-gates, testing-standards, ci-engineer, release-manager, CONTRIBUTING and CLAUDE.md now describe queueing a PR (gh pr merge <n> --auto) instead of rebasing it, and keep the old flow until the settings land. The design is decision-027. Not done in this PR: the repo settings (allow_auto_merge, the ruleset, strict=false). The lead applies them after merge with the commands in the notes and decision-027, and the first queued PR is the live check.
<!-- SECTION:FINAL_SUMMARY:END -->
