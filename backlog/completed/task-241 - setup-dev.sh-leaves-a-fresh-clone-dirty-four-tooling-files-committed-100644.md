---
id: TASK-241
title: 'setup-dev.sh leaves a fresh clone dirty: four tooling files committed 100644'
status: Done
assignee: []
created_date: '2026-10-13 15:52'
updated_date: '2026-10-13 17:09'
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

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Root cause: setup-dev.sh runs chmod +x over .githooks/*, .claude/hooks/*.sh, .claude/hooks/tests/*.sh and .claude/scripts/*.py; four files in those globs were committed 100644 (written by a file tool; always run as python3/bash <file>, so nothing failed locally).
Review round 1 (security, code, docs reviewers): the check now joins backslash-newline continuations (odd runs of trailing backslashes), refuses a continued line containing #, refuses [^...] and [[:class:]] globs (fnmatch reads them differently from bash), and fails when scripts/setup-dev.sh is missing; README, spec 08 §Testing, the pr-workflow skill, make help and the claude-tooling step name list the check.
Validation: check_file_modes.py listed exactly the four files before the fix and 0 errors after (26 files, 4 globs); test-tooling-scripts.sh 183/183 (29 check_file_modes rows); make tooling and make lint green; mutate.py --match "modes:" 22/22 killed; make mutate-changed in round 0 covered the mode-changed files' existing mutants (the two survivors then got rows); a fresh clone + setup-dev.sh leaves git status --porcelain empty.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Committed the four tooling files setup-dev.sh chmods (test-parser-boundaries.sh, check_digest_pins.py, lint_probes.py, probe_hook.py) as 100755, matching their shebangs and their 22 siblings, so a fresh clone stays clean after setup and record-review.py can attest. Added .claude/scripts/check_file_modes.py to make tooling: it reads every chmod in scripts/setup-dev.sh as bash would (continuations joined; any form it cannot read is refused), matches each glob against the git index, and fails on a matched file not committed 100755, a glob matching nothing, or a missing setup script. 29 case-table rows, 22 mutants (all killed); docs in CONTRIBUTING.md, README.md, spec 08, ci-engineer.md, the pr-workflow skill and make help.
<!-- SECTION:FINAL_SUMMARY:END -->
