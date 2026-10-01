---
id: TASK-156
title: >-
  Guard hooks: harden cmdparse against remaining shell-semantics bypasses
  (TASK-067 review)
status: To Do
assignee: []
created_date: '2026-10-01 19:36'
updated_date: '2026-10-01 22:16'
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
- [ ] #5 A command over ARG_MAX (about 1 MB) can't make a Bash-tool hook fail open: protect-data-dir, require-review and block-ai-attribution pass the payload to Python on stdin or through a temp file (today the env var makes exec fail with exit 126), or exit 2 whenever that step doesn't exit 0
- [ ] #6 protect-data-dir treats `git format-patch -o/--output-directory <dir>` as a write into <dir> (`git format-patch -o data/snapshots HEAD~1` is allowed today)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Deferred from the TASK-067 review gate by the main session's cap after four rounds. Cases are listed in the acceptance criteria; each was reproduced against origin/dev's hooks by the reviewers.

AC#5 and AC#6 came from the TASK-067 confirmation pass (after the final pass), checked against origin/dev's hooks. The deferral itself is the main session's cap decision for the TASK-067 review gate (2026-10-01): fix every Must and every regression in TASK-067, send pre-existing Should-level shell-semantics bypasses here.

2026-10-01 (PR #64 CI fix): `~` with HOME absent from the hook's environment now reads as the passwd home (as bash does), and `~` after `unset HOME` or `HOME=` in the command is unknown (fail closed). AC#3 remains only for a HOME present but set to '' in the hook's environment.

Correction to the note above: a HOME set to '' in the hook's environment is handled (`~` reads as ''), and a bare `cd` with HOME unset or '' is unknown (bash stays, zsh goes home). What remains of AC#3 is the reverse: HOME set in the hook's environment but '' in the agent's shell. The env_empty pass now reads `~` as the passwd home (right for an unset HOME), so a '' HOME is no longer tried there; check `~` both ways in that pass.
<!-- SECTION:NOTES:END -->
