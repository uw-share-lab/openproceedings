---
id: TASK-258
title: 'Decide: pin main''s required status checks to the GitHub Actions app'
status: To Do
assignee: []
created_date: '2026-10-17 08:45'
updated_date: '2026-10-17 09:12'
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
- [ ] #1 The owner decides; if yes, each required check on main names GitHub Actions as its source, verified with gh api before and after (JSON saved), and a decision-027 addendum records it with the rollback steps (app_id -1)
- [ ] #2 A release promotion PR into main still passes its required checks after the change
<!-- AC:END -->
