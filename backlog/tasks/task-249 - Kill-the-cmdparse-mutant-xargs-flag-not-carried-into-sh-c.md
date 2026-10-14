---
id: TASK-249
title: Kill the cmdparse mutant 'xargs flag not carried into sh -c'
status: To Do
assignee: []
created_date: '2026-10-14 22:59'
labels:
  - tooling
dependencies: []
ordinal: 175000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
make mutate on dev (ba8a0598) leaves the gates.json mutant 'xargs flag not carried into sh -c' (cmdparse.py: inner[0].via_xargs = inner[0].via_xargs or argv.via_xargs removed) alive: test-enforce-pr-workflow.sh, test-openproceedings-gates.sh and test-parser-boundaries.sh all pass with it applied. Found by TASK-243's mutation pass (fix/attribution-generated-by); that branch doesn't touch the xargs code. Add a row where an xargs-run sh -c's git push/commit is refused only because via_xargs is carried into the inner command, or document the mutant as equivalent with evidence.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A case row kills the mutant, or it is marked equivalent with a distinguishing negative case and a positive control
<!-- AC:END -->
