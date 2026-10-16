---
id: TASK-254
title: >-
  Mutation testing: compile-check mutants, reject ambiguous ones, and scope the
  remaining single-script tables
status: To Do
assignee: []
created_date: '2026-10-16 22:50'
labels:
  - tooling
  - tests
dependencies: []
priority: low
ordinal: 167000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by #153 and #158 (2026-10-16). (1) Six mutants' old strings occur more than once, so mutate.py tests only the first: dependabot.json 'GitHub's file list ignored' and 'a rename's old path on GitHub ignored'; gates.json 'gh pr edit not checked', 'dd branch removed', 'autofix: .prettierrc not watched' and 'pdd: find with no start is not .'. (2) Two gates.json mutants don't compile, so a table 'kills' them only because the edited file fails to compile: 'cmdparse: the join counts no arithmetic (TASK-164)' and 'modes: continuation not joined'. (3) test-dependabot.sh failed under load and was credited with killing mutate.py's 'no table timeout' mutant (TASK-238's bug class in another table). (4) test-mutate-shard.sh, test-merge-group-gate.sh and test-changelog.sh exercise one script each and could declare # mutate-scope: (TASK-238). (5) A misspelt # mutate-scope: path silently stops that table running.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 mutate.py (or a make tooling table) refuses a mutant whose old string matches more than once or whose result doesn't compile, and the eight mutants above are fixed
- [ ] #2 test-dependabot.sh can't be credited with a kill it didn't cause: it declares # mutate-scope: or its timing is load-robust, shown by a row
- [ ] #3 The three single-script tables declare # mutate-scope:, and mutate.py exits 2 when a declared path doesn't exist
<!-- AC:END -->
