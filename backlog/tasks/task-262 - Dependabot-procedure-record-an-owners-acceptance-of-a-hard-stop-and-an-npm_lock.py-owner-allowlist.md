---
id: TASK-262
title: >-
  Dependabot procedure: record an owner's acceptance of a hard stop, and an
  npm_lock.py owner allowlist
status: In Progress
assignee: []
created_date: '2026-10-18 14:16'
updated_date: '2026-10-18 14:27'
labels:
  - tooling
  - dependabot
dependencies: []
priority: low
ordinal: 175000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by the 2026-10-17/18 Dependabot batch (#163, #165): procedure §10 has no step for when the owner accepts a hard stop (where it is recorded, which checks are re-run, attesting that head only, the §11 summary), so the agent used a PR comment plus a PR-body line. npm_lock.py reads no allowlist, so an owner-accepted new package (#165: @codemirror/streamparser 6.0.0, comment 6245774665) keeps printing its PROBLEM line.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The procedure has an owner-accepts-a-hard-stop step naming the record, the re-run checks and the attestation
- [x] #2 npm_lock.py reads an owner-decision allowlist (package@version plus a comment URL), with case-table rows and a mutant
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
dependabot-review §10 gains 'When the owner accepts a hard stop (local only)': only the owner's own decision counts; record = a PR comment saying exactly what it covers (its URL cited in the body and in §11's merged line); re-run the reporting checker on the head (every other line clean) and every step after the stop, plus steps 5/6 if a commit was added after them; attest only that head, a new head is a new run. Intro and Hard stops section point to it; spec 08 §Dependabot says the same. npm_lock.py: OWNER_ACCEPTED (name@version -> comment URL), seeded with @codemirror/streamparser@6.0.0 -> PR #165 comment 6245774665 (verified: posted by the owner's account 2026-10-18). An accepted new package at that exact version is an ok line naming the URL and still goes through check_entry against the registry; another version is a new-package PROBLEM. A new entry's label no longer reads 'None -> version'. Case rows (dependabot_cases.py): accepted at that version (ok + matches the registry), another version (PROBLEM), accepted but integrity differs (PROBLEM). Four mutants in mutants/dependabot.json (allowlist never read, name-only match, registry check skipped, label).
<!-- SECTION:NOTES:END -->
