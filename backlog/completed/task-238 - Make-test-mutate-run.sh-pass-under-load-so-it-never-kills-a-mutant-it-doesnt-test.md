---
id: TASK-238
title: >-
  Make test-mutate-run.sh pass under load, so it never kills a mutant it doesn't
  test
status: Done
assignee: []
created_date: '2026-10-12 01:01'
updated_date: '2026-10-16 21:45'
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
- [x] #1 test-mutate-run.sh passes when run beside 8 parallel mutant runs at a load like make mutate-changed's
- [x] #2 A mutant of a file test-mutate-run.sh doesn't exercise is never reported KILLED by it (a row or check in test-mutate-run.sh or mutate.py's own table shows it)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Cause: mutate.py counts any failing table as a kill, and test-mutate-run.sh had wall-clock checks measured from the start of a nested mutate.py run (secs < 15 for 'stopped', 10 s to see a table start before an interrupt) and --table-timeout 5, which mutate.py refuses once a tiny table's baseline passes 0.5 s on a loaded machine. AC2: a table can declare the files it exercises in its header comment ('# mutate-scope: <file> ...', repo-relative, as a mutant's file); mutate.py (table_scope, can_kill) runs it only for a mutant whose file or also files include one of them, so a table that fails for any other reason can't be credited with another file's mutant. test-mutate-run.sh declares .claude/scripts/mutate.py; its fixture t-flaky.sh (fails in every mutant's copy) shows it: a mutant of src/u.txt survives and t-flaky never starts, a mutant of its declared file is killed by it, and a check reads the real table's scope as mutate.py only. Before the change t-flaky was credited with 13 rows' mutants. AC1: 'stopped' is checked from the log, interrupts wait up to 60 s and time from the signal, the hung-once row runs on a 5 s-floor fixture with no explicit timeout, and the hang row runs on a 120 s-floor fixture with --table-timeout 30, bounded [55 s, 200 s). Load test at 4b5ef950 (2026-10-16 17:23-17:43): mutate.py --jobs 8 over the 20 '(TASK-248)' cmdparse mutants, and test-mutate-run.sh three times beside it: 50/0 each (108 s, 104 s, 113 s); 1-minute load 16 before (other sessions, Spotlight), 29, 113 and 204 after runs 1-3. It also passed 46/0 earlier at a load of 67 from other sessions. 5 new mutants in mutants/mutate.json (scope ignored, scope read past the header, also files ignored by scope, first phase not limited to scope, explicit --table-timeout raised to the floor), all killed; all 31 'mutate run' mutants pass. Found on the way (follow-up): test-dependabot.sh failed under load and was credited with a mutate.py mutant ('no table timeout') on one run.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
mutate.py runs a table that declares '# mutate-scope:' files only for their mutants, so a flaky table can't be credited with another file's mutant; test-mutate-run.sh declares mutate.py and its timing checks are bounded by the sleeps they tell apart. Passed 50/0 three times beside mutate.py --jobs 8 (load up to 204).
<!-- SECTION:FINAL_SUMMARY:END -->
