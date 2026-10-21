---
id: TASK-271
title: Make main the default branch for the open-source repo
status: In Progress
assignee: []
created_date: '2026-10-20 13:40'
updated_date: '2026-10-21 01:42'
labels:
  - ci
  - process
dependencies: []
ordinal: 178000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The owner asked on 2026-10-20 for main to be the default branch before open-sourcing, dev to stay the integration branch for the org's writers, and forks to stay allowed (decision-052). Dependabot and scheduled workflows read the default branch, so their retargeting must reach main (with v0.4.1) before the switch.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Dependabot's four ecosystems set target-branch: dev, and the nightly's scheduled run checks out dev
- [x] #2 pr-gates' pr-base job fails any PR into main but the same-repo dev → main promotion, tested in test-merge-group-gate.sh
- [x] #3 CONTRIBUTING.md, the README and spec 08 tell a fork contributor to target dev
- [ ] #4 After v0.4.1 is tagged, in one step: the default branch is main and pr-base (app_id 15368) is required on main; spec 08 §Branch protection lists it and §Release step 5 says the promotion passes it; the next nightly's summary names the dev sha it tested
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
AC4 runs right after v0.4.1 is tagged (2026-10-21 UTC), in one step so there is no window without the check: gh api -X PATCH repos/uw-share-lab/openproceedings -f default_branch=main, and add pr-base (app_id 15368) to main's required status checks; then update spec 08 §Branch protection to the as-built state (pr-base in main's list) and §Release step 5 (the promotion passes pr-base). Dependabot security updates always target the default branch (GitHub docs); they are off here. Wording elsewhere (repo.ts links, pr-workflow, dependabot-review, ci-engineer, README Quickstart) is written to hold before and after the switch.

Gate round 1 added: nightly's resolve job (one sha for all 40 jobs), test-default-branch.sh (Dependabot target-branch, nightly wiring, resolve run with a fake git) with mutants/default-branch.json, pr-gates edited/main trigger assertion, fork-PR safety rules for maintainers (CONTRIBUTING, pr-workflow), repo.ts links to main, README Quickstart on main.

AC4 done except its last clause, 2026-10-21 ~01:34Z, right after v0.4.1 was tagged on main 66b5b1fe (release 0.4.1, promotion #181): pr-base (app_id 15368) added to main's classic required checks (strict false kept; the seven checks are now lint, test, claude-tooling, attribution, learnings, review-attested, pr-base), then default_branch=main, back to back. Spec 08 §Branch protection, the pr-base row and §Release step 5 updated to the as-built state on docs/main-default-as-built. Left: the next scheduled nightly (2026-10-21 ~12:42Z) must name the dev sha it tested in its summary; tick AC4 and complete the task after that run.
<!-- SECTION:NOTES:END -->
