---
id: TASK-258
title: 'Decide: pin main''s required status checks to the GitHub Actions app'
status: Done
assignee: []
created_date: '2026-10-17 08:45'
updated_date: '2026-10-19 11:49'
labels:
  - ci
  - security
  - decision
dependencies: []
ordinal: 171000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by the TASK-251 review (2026-10-17): the owner pinned dev's six required checks to GitHub Actions (app_id 15368), but main's branch protection still lists its required checks with app_id null, so a same-named check run from any app that can create check runs on this repo (for example the Claude GitHub App) satisfies them on a PR into main. Owner decision: it changes repo settings. The rollback sets app_id -1 (any app), not an omitted app_id, since GitHub re-selects the most recent provider when app_id is omitted.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The owner decides; if yes, each required check on main names GitHub Actions as its source, verified with gh api before and after (JSON saved), and a decision-027 addendum records it with the rollback steps (app_id -1)
- [x] #2 A release promotion PR into main still passes its required checks after the change
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Owner decision 2026-10-17 (about 18:50 EDT): yes. The lead PATCHed main's classic branch protection required_status_checks: strict false (unchanged) and the six checks lint, test, claude-tooling, attribution, learnings and review-attested each set to app_id 15368 (GitHub Actions). Before: the same six, strict false, each app_id null. The rest of main's protection was compared and is unchanged; main has no rulesets (rules/branches/main returns []). The before and after JSON were saved on the owner's machine, outside the repo (operator-only). Re-read live with gh api repos/uw-share-lab/openproceedings/branches/main/protection/required_status_checks before this record: six checks, each app_id 15368, strict false. decision-027's 2026-10-17 addendum records it with the rollback (app_id -1, main's branch in the API path); spec 08 §Branch protection, decision-048's addendum and the pr-workflow skill now say main is pinned.

AC #2 waits for the next dev→main promotion PR, which the owner holds until TASK-135 is settled; the task stays In Progress until that PR's required checks pass under the pin. A promotion head is dev's tip, already built by the merge queue and by push, so gh api --paginate 'repos/uw-share-lab/openproceedings/commits/<sha>/check-runs?check_name=<name>' returns several runs per name (on promotion #139's head a13658d9, learnings gave both skipped and success, and lint three successes). Every run of the six names on that sha must be app 15368; the proof is the run whose workflow run (the details_url's actions/runs/<id>) has event pull_request. On a same-repo promotion pr-gates.yml skips learnings and review-attested, so those two read conclusion skipped from app 15368 rather than a gate run; lint, test, claude-tooling and attribution read success.

AC#2: promotion PR #173 (dev → main for 0.4.0) reported every required check from the pinned app and merged CLEAN as fa9c1c07, tagged v0.4.0.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
main's required checks are pinned to the GitHub Actions app (decision-027 addendum, rollback app_id -1); the 0.4.0 promotion (#173) passed them.
<!-- SECTION:FINAL_SUMMARY:END -->
