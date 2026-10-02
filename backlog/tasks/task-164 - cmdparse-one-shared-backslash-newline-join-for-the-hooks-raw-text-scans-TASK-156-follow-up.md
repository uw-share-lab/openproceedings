---
id: TASK-164
title: >-
  cmdparse: one shared backslash-newline join for the hooks' raw-text scans
  (TASK-156 follow-up)
status: In Progress
assignee:
  - '@jeevanparmar'
created_date: '2026-10-02 09:27'
updated_date: '2026-10-02 20:49'
labels:
  - security
  - tooling
  - deferred
dependencies:
  - TASK-156
  - TASK-169
references:
  - .claude/hooks/lib/cmdparse.py
  - .claude/hooks/require-review.sh
  - .claude/hooks/enforce-pr-workflow.sh
priority: medium
ordinal: 134000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Source: TASK-156 review (2026-10-02), deferred. Bash deletes a backslash-newline outside single quotes (and outside a heredoc body), so `git pu\<newline>sh` runs `git push`. cmdparse.preprocess() already joins these before tokenizing, so every check that reads cmdparse's words sees the joined command. The gap is the raw-text scans that run on the command string before or instead of preprocess, each with its own ad hoc join: `_case_cut_short` (added by TASK-156's PR), require-review.sh's line-continuation search (around line 233) and enforce-pr-workflow.sh's parse-failure plain-text fallback (around line 563). Each copy can drift from preprocess's rules (single quotes, heredoc bodies). Replace them with one cmdparse helper that preprocess also uses, so every raw-text scan joins continuations exactly as bash does.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 cmdparse exposes one backslash-newline join (outside single quotes and heredoc bodies) that preprocess() uses; every raw-text scan in the hooks (list them in the notes) calls it instead of its own join
- [x] #2 Case-table rows for each raw-text path: a keyword split by a continuation is blocked, and a backslash-newline inside single quotes or a quoted heredoc body is not joined
- [ ] #3 Each new branch has a mutant in .claude/scripts/mutants/gates.json; `make tooling` and `python3 .claude/scripts/mutate.py --changed` pass
- [x] #4 Probes in the new rows use TASK-169's helper (data only, never an executed shell)
- [x] #5 The shared join never raises on input it can't scan, and no fail-closed fallback blocks less than it does today (those fallbacks run after a parse failure and today join every backslash-newline); a case-table row proves it with a stray quote before a split `pu\<newline>sh`
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Preserve recovered implementation; reproduce regressions, scan sed script files, add deterministic join and case-folding coverage, run lint/tooling/changed mutation checks, update docs and learnings, complete tasks and commit for independent review.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Recovered shared join used by preprocess, cmdparse case cut-short, require-review parse-failure net, enforce-pr-workflow fallback, and both attribution raw-text scans. Added exact joined-text heredoc boundary rows; isolated mutation checks kill both previous join survivors and the worktree case-comparison survivor. Node22 make lint and initial make tooling passed (839 gate rows, 118 tooling rows); final stable tooling rerun and changed mutation verification pending.
<!-- SECTION:NOTES:END -->
