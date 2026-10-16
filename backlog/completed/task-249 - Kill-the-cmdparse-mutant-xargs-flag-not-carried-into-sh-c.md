---
id: TASK-249
title: Kill the cmdparse mutant 'xargs flag not carried into sh -c'
status: Done
assignee: []
created_date: '2026-10-14 22:59'
updated_date: '2026-10-16 21:45'
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
- [x] #1 A case row kills the mutant, or it is marked equivalent with a distinguishing negative case and a positive control
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Killed by a row, not marked equivalent: test-enforce-pr-workflow.sh, on feature/x, `echo -- --amend | xargs sh -c 'git commit -m wip "$@"' sh` is refused only because via_xargs is carried into the sh -c's commit (with the mutant the commit on a feature branch passes); positive control `echo x | xargs sh -c 'git log -1 "$@"' sh` is allowed. The older push row stayed green under the mutant because its unresolved "$@" refspec is refused anyway.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Killed by a row: an xargs-run sh -c's commit on a feature branch is refused only because via_xargs is carried into the inner command; positive control with git log.
<!-- SECTION:FINAL_SUMMARY:END -->
