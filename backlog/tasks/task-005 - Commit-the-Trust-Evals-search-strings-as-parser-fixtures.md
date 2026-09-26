---
id: TASK-005
title: Commit the Trust-Evals search strings as parser fixtures
status: To Do
assignee: []
created_date: '2026-09-25 22:06'
updated_date: '2026-09-26 01:07'
labels:
  - query
  - eval
milestone: m-1
dependencies: []
references:
  - .claude/skills/scholar-syntax-compat/SKILL.md
ordinal: 5000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
scholar-syntax-compat needs the protocol's six search strings verbatim; they are not in any repo yet (they live in the protocol document).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Strings copied verbatim into backend/tests/fixtures/queries/trust-evals.txt with their protocol names
- [ ] #2 Golden canonical-form snapshots for each (M1)
<!-- AC:END -->
