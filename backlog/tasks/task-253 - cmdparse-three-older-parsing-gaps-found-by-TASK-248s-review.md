---
id: TASK-253
title: 'cmdparse: three older parsing gaps found by TASK-248''s review'
status: To Do
assignee: []
created_date: '2026-10-16 22:50'
labels:
  - tooling
dependencies: []
priority: low
ordinal: 166000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found while reviewing TASK-248 (PR #158, 2026-10-16); all predate that branch and are on dev. (1) _strip_prefixes doesn't split a short-option cluster that ends in a value-taking option, so the value is read as the command: sudo -nu root git push, flock -nw 5 <file> ..., doas -nu root .... (2) env -C dir and sudo -D dir move the parser's directory for every later command instead of only the one they run: env -C /tmp true; git commit is judged as if it ran in /tmp. (3) sh -c '...' >> file and eval ... >> file drop their own redirects, so a write to a protected path through them isn't seen. The hooks are agent guardrails, not a security boundary; keep the fix bounded and fail closed.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A short-option cluster ending in a value-taking option is split for sudo, doas, flock and the other getopt-style wrappers, or the command is treated as unknown and refused
- [ ] #2 env -C and sudo -D change the directory only for the command they run
- [ ] #3 sh -c and eval keep their own redirects, so protect-data-dir sees the write
- [ ] #4 Each case has rows (probes as data only) in the affected gates' tables and a killed mutant in .claude/scripts/mutants/gates.json
<!-- AC:END -->
