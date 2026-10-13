---
id: TASK-241
title: 'setup-dev.sh leaves a fresh clone dirty: four tooling files committed 100644'
status: In Progress
assignee: []
created_date: '2026-10-13 15:52'
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
- [ ] #1 The four files are committed 100755, consistent with their shebangs and sibling files
- [ ] #2 A `make tooling` check fails when a tracked file the setup script chmods +x is not committed 100755, when a chmod glob matches no tracked file, and when a chmod in the script has a form it cannot read
- [ ] #3 Case-table rows cover the check, and its mutants are killed (`make mutate-changed`)
- [ ] #4 Docs describe the check as built
<!-- AC:END -->
