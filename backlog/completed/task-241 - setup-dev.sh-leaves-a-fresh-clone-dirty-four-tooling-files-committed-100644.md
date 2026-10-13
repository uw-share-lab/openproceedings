---
id: TASK-241
title: 'setup-dev.sh leaves a fresh clone dirty: four tooling files committed 100644'
status: Done
assignee: []
created_date: '2026-10-13 15:52'
updated_date: '2026-10-13 16:28'
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
Validation: check_file_modes.py listed exactly those four before the fix and 0 errors after (26 files, 4 globs); test-tooling-scripts.sh 174/174; make tooling and make lint green; make mutate-changed: 52 mutants, the 15 new "modes:" mutants all killed after two rows were added for the two first-round survivors (* crossing / and an unanchored segment match).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Committed the four tooling files setup-dev.sh chmods (test-parser-boundaries.sh, check_digest_pins.py, lint_probes.py, probe_hook.py) as 100755, matching their shebangs and their 22 siblings, so a fresh clone stays clean after setup and record-review.py can attest. Added .claude/scripts/check_file_modes.py to make tooling: it reads every chmod in scripts/setup-dev.sh (refusing forms it cannot read), matches each glob against the git index as bash would, and fails on a matched file not committed 100755 or a glob matching nothing. 20 case-table rows, 15 mutants (all killed), docs in CONTRIBUTING.md, ci-engineer.md and spec 08.
<!-- SECTION:FINAL_SUMMARY:END -->
