---
id: TASK-170
title: >-
  block-ai-attribution: read a commit-message file named through a variable or
  by head/tail/sed (TASK-156 follow-up)
status: In Progress
assignee:
  - '@jeevanparmar'
created_date: '2026-10-02 10:33'
updated_date: '2026-10-02 20:53'
labels:
  - security
  - tooling
  - deferred
dependencies: []
references:
  - .claude/hooks/block-ai-attribution.sh
  - .claude/hooks/lib/cmdparse.py
priority: medium
ordinal: 140000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Source: TASK-156 security review (PR #83, 2026-10-02), deferred; the gap predates TASK-156. block-ai-attribution reads a commit-message file only when a command substitution names it to `cat`, and it passes the raw word as the file name. So `F=msg.txt; git commit -m "$(cat "$F")"` looks for a file literally named `$F`, and `git commit -m "$(head -5 msg.txt)"` (or tail, sed) reads no file at all; an attribution trailer in that file is never scanned. Expand the word with cmdparse's `expand_known` before reading it, decide which readers besides cat are read (head, tail, sed -n, and so on), and fail closed when a substitution reads a file the hook can't resolve or a reader it doesn't model.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A commit-message file named through a variable the hook can resolve (`F=msg.txt; … "$(cat "$F")"`) is read and scanned
- [x] #2 head, tail and sed readers are either read (the file's whole text scanned) or refused; the choice is written in the hook's comment and spec 08's hook table
- [x] #3 A substitution that reads a file named by an argument the hook can't resolve (an unknown variable, or a file argument to a reader it doesn't model) is refused, not passed; a substitution that reads no file (`$(date)`, `$(git log -1 --format=%s)`) is still allowed
- [ ] #4 Block and allow rows in the hook case table (including an allow row for a substitution that reads no file), with probes passed as data (TASK-169), and a mutant per new branch in .claude/scripts/mutants/gates.json; `make tooling` and `python3 .claude/scripts/mutate.py --changed` pass
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Preserve recovered implementation; reproduce regressions, scan sed script files, add deterministic join and case-folding coverage, run lint/tooling/changed mutation checks, update docs and learnings, complete tasks and commit for independent review.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Five sed script-file recovery rows failed before fix. reader_files now scans separate/attached -f and --file arguments; unknown script file values refuse. Added variable, attached unknown, and clean script allow rows. Initial tooling839/0; changed mutation verification pending.

Safe JSON probe found clustered -nfFILE script bypass. Fixed bundled short-option consumption through first e/f, with i backup suffix treated separately and unknown bundles refused. Added12 rows and8 mutants;11 focused safe JSON probes pass. Cancelled prior validation runners before changing code; restarted stable tooling/lint/changed mutations.413 changed mutants selected,0 stale patterns.
<!-- SECTION:NOTES:END -->
