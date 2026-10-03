---
id: TASK-170
title: >-
  block-ai-attribution: read a commit-message file named through a variable or
  by head/tail/sed (TASK-156 follow-up)
status: Done
assignee:
  - '@jeevanparmar'
created_date: '2026-10-02 10:33'
updated_date: '2026-10-03 08:06'
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
- [x] #4 Block and allow rows in the hook case table (including an allow row for a substitution that reads no file), with probes passed as data (TASK-169), and a mutant per new branch in .claude/scripts/mutants/gates.json; `make tooling` and `python3 .claude/scripts/mutate.py --changed` pass
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Preserve recovered implementation; reproduce regressions, scan sed script files, add deterministic join and case-folding coverage, run lint/tooling/changed mutation checks, update docs and learnings, complete tasks and commit for independent review.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Five sed script-file recovery rows failed before fix. reader_files now scans separate/attached -f and --file arguments; unknown script file values refuse. Added variable, attached unknown, and clean script allow rows. Initial tooling839/0; changed mutation verification pending.

Safe JSON probe found clustered -nfFILE script bypass. Fixed bundled short-option consumption through first e/f, with i backup suffix treated separately and unknown bundles refused. Added12 rows and8 mutants;11 focused safe JSON probes pass. Cancelled prior validation runners before changing code; restarted stable tooling/lint/changed mutations.413 changed mutants selected,0 stale patterns.

Round1 reviewer confirmed -- termination bypass for cat/head/tail and sed:4 safe red JSON probes allowed banned leading-dash files. Added end-options state, literal filenames afterward and preserved implicit sed expression.15 focused green JSON probes pass;15 gate rows and4 mutants added; final full checks pending.

Complete official make mutate-changed on reviewed source 9d035a1877e806e8ea11b5c9fde7ca3cc557812a: 417 mutants: 0 problem(s), exit 0; 413 killed and four independently audited equivalent survivors, no stale patterns. Raw /tmp/hooks-official-linux-9d.log, exact .head, .exit contains 0; post-run host/container tracked-byte hashes unchanged. Fresh Node22 make lint and make tooling both passed exit 0 (/tmp/hooks-lint-9d.log and /tmp/hooks-tooling-9d.log). Interrupted earlier runs remain diagnostic only. Final metadata commit gates and exact-head review follow.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Attribution scans resolved whole files for cat/head/tail/sed, including script files, bundled options and literal filenames after --; unknown readers or file values refuse. Safe data-only block/allow controls and complete official 417-mutant validation plus make tooling passed exit 0.
<!-- SECTION:FINAL_SUMMARY:END -->
