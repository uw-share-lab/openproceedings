---
id: TASK-251
title: 'Decide: pin dev''s required status checks to the GitHub Actions app'
status: To Do
assignee: []
created_date: '2026-10-16 22:50'
updated_date: '2026-10-16 22:51'
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
- [ ] #1 The owner decides; if yes, each required check in branch protection and ruleset 24351281 names GitHub Actions as its source, verified with gh api, and decision-027 or decision-048 records it with the rollback steps
- [ ] #2 A PR still merges through the queue after the change (one live PR checked)
<!-- AC:END -->
