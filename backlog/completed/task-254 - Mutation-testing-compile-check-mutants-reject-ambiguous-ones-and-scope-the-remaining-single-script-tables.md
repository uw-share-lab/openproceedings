---
id: TASK-254
title: >-
  Mutation testing: compile-check mutants, reject ambiguous ones, and scope the
  remaining single-script tables
status: Done
assignee: []
created_date: '2026-10-16 22:50'
updated_date: '2026-10-19 00:51'
labels:
  - tooling
  - tests
dependencies: []
priority: low
ordinal: 167000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by #153 and #158 (2026-10-16). (1) Twelve mutants' old strings occur more than once, so mutate.py tests only the first (it replaces the first match): dependabot.json 'GitHub's file list ignored' and 'a rename's old path on GitHub ignored'; gates.json 'gh pr edit not checked', 'dd branch removed', 'autofix: .prettierrc not watched' and 'pdd: find with no start is not .'; merge-group.json (all on .github/workflows/pr-gates.yml, found in the review of the branch that filed this task) 'pr-gates: first job's event guard dropped', 'pr-gates: merge_group step loses its event condition', 'pr-gates: head ref not passed', 'pr-gates: pull-requests read dropped', 'pr-gates: learnings job skipped on merge_group by a job-level if' and 'pr-gates: merge_group step if: weakened'. (2) Two gates.json mutants don't compile, so a table 'kills' them only because the edited file fails to compile: 'cmdparse: the join counts no arithmetic (TASK-164)' and 'modes: continuation not joined'. (3) test-dependabot.sh failed under load and was credited with killing mutate.py's 'no table timeout' mutant (TASK-238's bug class in another table). (4) test-mutate-shard.sh, test-merge-group-gate.sh and test-changelog.sh exercise one script each and could declare # mutate-scope: (TASK-238). (5) A misspelt # mutate-scope: path silently stops that table running.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 test-dependabot.sh can't be credited with a kill it didn't cause: it declares # mutate-scope: or its timing is load-robust, shown by a row
- [x] #2 The three single-script tables declare # mutate-scope:, and mutate.py exits 2 when a declared path doesn't exist
- [x] #3 mutate.py (or a make tooling table) refuses a mutant whose old string matches more than once or whose result doesn't compile, and the fourteen mutants above are fixed
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-18 (branch fix/cmdparse-wrapper-options, with TASK-253): mutate.py vets each mutant before it runs a table (vet): STALE (old text gone from a file), AMBIGUOUS (it occurs more than once) or UNCOMPILABLE (the edit stops a file compiling that compiled: .py compiled, .json parsed, shell by suffix or #! line through bash -n with each <<'PY' heredoc compiled; only the parts the edit changed are checked). --check vets the selected mutants in processes and runs no table (about 2 s for 1,650); make tooling and the nightly's first shard run it (the nightly's inline stale check is gone). check_scopes exits 2 on a # mutate-scope: path that doesn't exist. The vetting found 18: the 12 ambiguous ones listed, the 2 uncompilable ones listed, 3 more uncompilable (PR gate: xargs verdict dropped; pdd: perl read like sed; protect-data-dir: ruby -i not in place) and one this branch made stale; all rewritten to the occurrence they were killed on (git log -S for dd and find), with new texts that compile. Scope: test-dependabot.sh declares the 8 /dependabot-review scripts; test-mutate-shard.sh mutate.py; test-changelog.sh changelog.py; test-merge-group-gate.sh merge_group_gate.py plus the four workflows its wiring row reads (pr-gates, test, lint, claude-tooling). Rows in test-mutate-run.sh: the vet fixture (v-* mutants), the misspelt-scope fixture, and the scope declarations.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
mutate.py vets each mutant (STALE, AMBIGUOUS, UNCOMPILABLE: .py compiled, .json parsed, shell via bash -n with <<'PY' heredocs compiled) before running a table; --check runs only that, in make tooling and the nightly's first shard; a missing # mutate-scope: path exits 2. The 14 listed mutants plus 3 more uncompilable ones were rewritten; test-dependabot.sh, test-mutate-shard.sh, test-merge-group-gate.sh and test-changelog.sh declare their scope. Rows in test-mutate-run.sh.
<!-- SECTION:FINAL_SUMMARY:END -->
