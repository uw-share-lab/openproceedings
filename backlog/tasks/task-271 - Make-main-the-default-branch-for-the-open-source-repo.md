---
id: TASK-271
title: Make main the default branch for the open-source repo
status: In Progress
assignee: []
created_date: '2026-10-20 13:40'
updated_date: '2026-10-20 13:41'
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
- [ ] #4 After v0.4.1 is tagged: the default branch is main, pr-base is required on main, and spec 08 says so
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
AC4 runs after v0.4.1 is tagged (2026-10-21): gh api -X PATCH repos/uw-share-lab/openproceedings -f default_branch=main; add pr-base to main's required status checks (app_id 15368); update spec 08 §Branch protection to the as-built state. Dependabot security updates always target the default branch (GitHub docs); they are off here.
<!-- SECTION:NOTES:END -->
