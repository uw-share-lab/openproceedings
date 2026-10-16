---
id: TASK-254
title: >-
  Mutation testing: compile-check mutants, reject ambiguous ones, and scope the
  remaining single-script tables
status: To Do
assignee: []
created_date: '2026-10-16 22:50'
updated_date: '2026-10-16 23:17'
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
- [ ] #1 test-dependabot.sh can't be credited with a kill it didn't cause: it declares # mutate-scope: or its timing is load-robust, shown by a row
- [ ] #2 The three single-script tables declare # mutate-scope:, and mutate.py exits 2 when a declared path doesn't exist
- [ ] #3 mutate.py (or a make tooling table) refuses a mutant whose old string matches more than once or whose result doesn't compile, and the fourteen mutants above are fixed
<!-- AC:END -->
