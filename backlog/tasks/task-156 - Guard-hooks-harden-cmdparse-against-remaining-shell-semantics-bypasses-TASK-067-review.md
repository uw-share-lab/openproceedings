---
id: TASK-156
title: >-
  Guard hooks: harden cmdparse against remaining shell-semantics bypasses
  (TASK-067 review)
status: To Do
assignee: []
created_date: '2026-10-01 19:36'
labels:
  - security
  - tooling
dependencies: []
references:
  - .claude/hooks/lib/cmdparse.py
priority: medium
ordinal: 131000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Source: TASK-067 review gate (final security-reviewer and qa-auditor pass, 2026-10-01). The guard hooks (.claude/hooks/*, lib/cmdparse.py) are guardrails against a cooperating agent's mistakes, not an access-control boundary: anything that deliberately evades them still meets git's own refusals, CI (attribution, review-attested) and branch protection. TASK-067 fixed every Must, every regression it introduced and every incomplete fix of its own claims; these pre-existing (on origin/dev before TASK-067) Should-level bypasses were deferred so the gate would end. Prefer simple fail-closed rules over modelling more bash.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 block-ai-attribution also scans the parsed argv words, so a trailer split by shell quoting (`-m 'Co-Authored-By: Cl''aude <noreply@anthr''opic.com>'`) is refused
- [ ] #2 A git push, commit-maker or data/ write inside a quoted command substitution (`x="$(git push origin HEAD:dev)"`) or backquotes is read and checked like a top-level command, or refused
- [ ] #3 A bare `~` (and `~/…`) is also checked with HOME empty for every gate, not only pushes (`cd ~ && rm -rf data` with an empty HOME)
- [ ] #4 Each case has block rows and a mutant in gates.json; make tooling and mutate.py --changed pass
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Deferred from the TASK-067 review gate by the main session's cap after four rounds. Cases are listed in the acceptance criteria; each was reproduced against origin/dev's hooks by the reviewers.
<!-- SECTION:NOTES:END -->
