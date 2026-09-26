---
id: TASK-005
title: Commit the Trust-Evals search strings as parser fixtures
status: Done
assignee:
  - '@jeevan'
created_date: '2026-09-25 22:06'
updated_date: '2026-09-26 03:33'
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
- [x] #2 Golden canonical-form snapshots for each (M1)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
trust-evals.txt holds all ten strings, extracted programmatically from the protocol text the user shared (2026-09-25 session); AC2 (canonical snapshots) lands with task-015's Scholar mode, since six of the strings use source: and one uses PoP syntax.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
backend/tests/fixtures/queries/trust-evals.txt: all ten protocol strings (seven main variants incl. Most Updated, narrow, human-centred, LLM-as-judge), extracted programmatically from the protocol text. The primary string (main-7-most-updated) was confirmed by the review lead and is pinned. Canonical/hash/identification snapshots in tests/golden/trust_evals_canonical.json (Scholar mode).
<!-- SECTION:FINAL_SUMMARY:END -->
