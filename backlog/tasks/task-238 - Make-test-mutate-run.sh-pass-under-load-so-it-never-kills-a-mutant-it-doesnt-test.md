---
id: TASK-238
title: >-
  Make test-mutate-run.sh pass under load, so it never kills a mutant it doesn't
  test
status: To Do
assignee: []
created_date: '2026-10-12 01:01'
labels:
  - ci
  - tests
dependencies: []
ordinal: 166000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by qa-auditor on the chore/dependabot-uv-0x-minor review gate (2026-10-11): .claude/scripts/tests/test-mutate-run.sh passes alone (37/0, ~50 s) but fails when make mutate-changed runs mutants in parallel on a loaded machine. mutate.py counts any failing table as a kill, so a flaky table reports a surviving mutant as KILLED: in that run 15 of 17 docker_digest.py mutants were credited to test-mutate-run.sh, which never runs docker_digest.py. The comment that made it a first-phase table for every dependabot mutant (it named dependabot_cases.py, which mutate.py's table_text reads) was reworded on that branch; the timing sensitivity remains, and a mutant that survives its first tables still runs test-mutate-run.sh. Spec 08 §Mutation testing.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 test-mutate-run.sh passes when run beside 8 parallel mutant runs at a load like make mutate-changed's
- [ ] #2 A mutant of a file test-mutate-run.sh doesn't exercise is never reported KILLED by it (a row or check in test-mutate-run.sh or mutate.py's own table shows it)
<!-- AC:END -->
