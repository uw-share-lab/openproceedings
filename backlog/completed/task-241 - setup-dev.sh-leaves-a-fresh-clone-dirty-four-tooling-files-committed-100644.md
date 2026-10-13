---
id: TASK-241
title: 'setup-dev.sh leaves a fresh clone dirty: four tooling files committed 100644'
status: Done
assignee: []
created_date: '2026-10-13 15:52'
updated_date: '2026-10-13 18:04'
labels:
  - tooling
  - bug
dependencies: []
priority: medium
ordinal: 167000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The weekly cloud routine (2026-10-13) found that on a fresh clone `scripts/setup-dev.sh` runs `chmod +x` over `.claude/hooks/tests/*.sh` and `.claude/scripts/*.py`, and four committed files in those globs were 100644 (test-parser-boundaries.sh, check_digest_pins.py, lint_probes.py, probe_hook.py). The chmod showed as a mode change in `git status`, and the dirty tree blocks `record-review.py` ("working tree is not clean"), so the routine had to set core.fileMode=false. Nothing stopped a new script in those globs from being committed 100644 again.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The four files are committed 100755, consistent with their shebangs and sibling files
- [x] #2 A `make tooling` check fails when a tracked file the setup script chmods +x is not committed 100755, when a chmod glob matches no tracked file, and when a chmod in the script has a form it cannot read
- [x] #3 Case-table rows cover the check, and its mutants are killed (`make mutate-changed`)
- [x] #4 Docs describe the check as built
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Find what in setup-dev.sh sets the bit: its one `chmod +x` over four globs.
2. Decide on evidence: the four files have shebangs and all 22 siblings in the same globs are 100755, so commit them 100755 (keep the chmod as a safety net).
3. Add .claude/scripts/check_file_modes.py to make tooling: read every chmod in setup-dev.sh (fail closed on forms it cannot read), match each glob against git's index as bash would, require 100755 and at least one match.
4. Case-table rows in test-tooling-scripts.sh, mutants in gates.json, docs (CONTRIBUTING, ci-engineer, spec 08) and a learnings entry.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Root cause: setup-dev.sh runs chmod +x over .githooks/*, .claude/hooks/*.sh, .claude/hooks/tests/*.sh and .claude/scripts/*.py; four files in those globs were committed 100644 (written by a file tool; always run as python3/bash <file>, so nothing failed locally).
Review round 1 (security, code, docs): the check joins backslash-newline continuations (odd runs of trailing backslashes), refuses a continued line containing #, refuses [^...] globs, and fails when scripts/setup-dev.sh is missing; README, spec 08 §Testing, the pr-workflow skill, make help and the claude-tooling step name list the check.
Review round 2 (security, qa, code): # starts a comment only at the start of a word, as in bash, and a chmod after one is refused; any [[ glob form, shopt, GLOBIGNORE and a cd/pushd/popd other than cd to the repo root are refused; a chmod line with quotes, backslashes or a redirection is refused.
Validation: check_file_modes.py listed exactly the four files before the fix and 0 errors after (26 files, 4 globs); test-tooling-scripts.sh 195/195 (41 check_file_modes rows); make tooling and make lint green; mutate.py --match "modes:" 33/33 killed; make mutate-changed in round 0 covered the mode-changed files' existing mutants; a fresh clone + setup-dev.sh leaves git status --porcelain empty (qa-auditor also showed the merge-base leaves exactly the four files dirty).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Committed the four tooling files setup-dev.sh chmods (test-parser-boundaries.sh, check_digest_pins.py, lint_probes.py, probe_hook.py) as 100755, matching their shebangs and their 22 siblings, so a fresh clone stays clean after setup and record-review.py can attest. Added .claude/scripts/check_file_modes.py to make tooling: it reads every chmod in scripts/setup-dev.sh as bash would (continuations joined, comments only at a word start; any form it cannot read is refused), matches each glob against the git index, and fails on a matched file not committed 100755, a glob matching nothing, or a missing setup script. 41 case-table rows, 33 mutants (all killed); docs in CONTRIBUTING.md, README.md, spec 08, ci-engineer.md, the pr-workflow skill and make help.
<!-- SECTION:FINAL_SUMMARY:END -->
