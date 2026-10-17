---
id: TASK-251
title: 'Decide: pin dev''s required status checks to the GitHub Actions app'
status: In Progress
assignee: []
created_date: '2026-10-16 22:50'
updated_date: '2026-10-17 08:45'
labels:
  - ci
  - security
  - decision
dependencies: []
ordinal: 164000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by the #153 review (2026-10-16, decision-048 addendum): dev's six required checks show app_id null in branch protection and the merge-queue ruleset, so a check run with the same name written by any app able to create check runs on this repo would satisfy the requirement. Pinning each required check to GitHub Actions (app_id 15368) closes that. Owner decision: it changes repo settings, and the rollback note in decision-027 must stay valid.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The owner decides; if yes, each required check in branch protection and ruleset 24351281 names GitHub Actions as its source, verified with gh api, and decision-027 or decision-048 records it with the rollback steps
- [ ] #2 A PR still merges through the queue after the change (one live PR checked)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Owner decision 2026-10-17 (about 03:21 EDT): yes. Before the change, every required check on dev's queue commit a49a7cba (#159's gh-readonly-queue build) and on #159's head de03b796 was a check run from github-actions (app 15368); commits/<sha>/status held no commit status for any of them (a claude check suite exists on both commits but holds no runs). Ruleset 24351281 has only its merge_queue rule (no required_status_checks), and rules/branches/dev lists only that rule, so the checks are required in the classic branch protection alone. Applied about 03:25 EDT: PATCH branches/dev/protection/required_status_checks with checks [{context, app_id: 15368}] x6, strict false; verified: all six read app_id 15368, and the rest of the protection JSON is unchanged field for field. Pre-change JSON kept in the session scratchpad (t251-protection-before.json, t251-rsc-before.json, t251-ruleset-24351281-before.json). decision-027 addendum (2026-10-17) records the commands, the evidence and the rollback (app_id -1, any app); spec 08 §Branch protection, its cloud-routine paragraph and the pr-workflow skill say it. AC #2: this task's PR is the first queued after the change; it reaches dev only through a queue build whose six check runs met the pinned requirement, so the AC holds wherever this commit is on dev.

Review round 1 (security-reviewer): the rollback sends app_id -1, not null. GitHub's REST docs: omitting app_id makes GitHub pick the app that recently provided the check, and -1 allows any app (docs read 2026-10-17); decision-027's addendum has the rollback with a verify step and the legacy contexts fallback. main's six checks stay app_id null (outside this decision); spec 08 says so, and the lead was told, to file a follow-up if the owner wants it.
<!-- SECTION:NOTES:END -->
