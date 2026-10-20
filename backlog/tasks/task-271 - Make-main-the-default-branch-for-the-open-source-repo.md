---
id: TASK-271
title: Make main the default branch for the open-source repo
status: In Progress
assignee: []
created_date: '2026-10-20 13:40'
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
- [ ] #1 Dependabot's four ecosystems set target-branch: dev, and the nightly's scheduled run checks out dev
- [ ] #2 pr-gates' pr-base job fails any PR into main but the same-repo dev → main promotion, tested in test-merge-group-gate.sh
- [ ] #3 CONTRIBUTING.md, the README and spec 08 tell a fork contributor to target dev
- [ ] #4 After v0.4.1 is tagged: the default branch is main, pr-base is required on main, and spec 08 says so
<!-- AC:END -->
