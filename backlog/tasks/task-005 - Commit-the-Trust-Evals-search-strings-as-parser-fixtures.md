---
id: TASK-005
title: Commit the Trust-Evals search strings as parser fixtures
status: In Progress
assignee:
  - '@jeevan'
created_date: '2026-09-25 22:06'
updated_date: '2026-09-26 02:53'
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
- [x] #1 Strings copied verbatim into backend/tests/fixtures/queries/trust-evals.txt with their protocol names
- [ ] #2 Golden canonical-form snapshots for each (M1)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
trust-evals.txt holds all ten strings, extracted programmatically from the protocol text the user shared (2026-09-25 session); AC2 (canonical snapshots) lands with task-015's Scholar mode, since six of the strings use source: and one uses PoP syntax.
<!-- SECTION:NOTES:END -->
