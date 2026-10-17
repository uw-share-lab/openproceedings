---
id: TASK-258
title: 'Decide: pin main''s required status checks to the GitHub Actions app'
status: In Progress
assignee: []
created_date: '2026-10-17 08:45'
updated_date: '2026-10-17 22:57'
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
- [ ] #2 A release promotion PR into main still passes its required checks after the change
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Owner decision 2026-10-17 (about 18:50 EDT): yes. The lead PATCHed main's classic branch protection required_status_checks: strict false (unchanged) and the six checks lint, test, claude-tooling, attribution, learnings and review-attested each set to app_id 15368 (GitHub Actions). Before: the same six, strict false, each app_id null. The rest of main's protection was compared and is unchanged; main has no rulesets (rules/branches/main returns []). The before and after JSON were saved on the owner's machine, outside the repo (operator-only). Re-read live with gh api repos/uw-share-lab/openproceedings/branches/main/protection/required_status_checks before this record: six checks, each app_id 15368, strict false. decision-027's 2026-10-17 addendum records it with the rollback (app_id -1, main's branch in the API path); spec 08 §Branch protection, decision-048's addendum and the pr-workflow skill now say main is pinned.

AC #2 waits for the next dev→main promotion PR, which the owner holds until TASK-135 is settled; the task stays In Progress until that PR's required checks pass under the pin. On a same-repo promotion pr-gates.yml skips learnings and review-attested, so those two show conclusion skipped from app 15368 rather than a gate run; the proof reads each required check run's .app.id and .conclusion (gh api 'repos/uw-share-lab/openproceedings/commits/<sha>/check-runs?check_name=<name>') and expects 15368 with success for lint, test, claude-tooling and attribution, and skipped for the other two.
<!-- SECTION:NOTES:END -->
