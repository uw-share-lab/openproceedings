---
id: TASK-164
title: >-
  cmdparse: one shared backslash-newline join for the hooks' raw-text scans
  (TASK-156 follow-up)
status: Done
assignee:
  - '@jeevanparmar'
created_date: '2026-10-02 09:27'
updated_date: '2026-10-03 08:06'
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
- [x] #3 Each new branch has a mutant in .claude/scripts/mutants/gates.json; `make tooling` and `python3 .claude/scripts/mutate.py --changed` pass
- [x] #4 Probes in the new rows use TASK-169's helper (data only, never an executed shell)
- [x] #5 The shared join never raises on input it can't scan, and no fail-closed fallback blocks less than it does today (those fallbacks run after a parse failure and today join every backslash-newline); a case-table row proves it with a stray quote before a split `pu\<newline>sh`
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Preserve recovered implementation; reproduce regressions, scan sed script files, add deterministic join and case-folding coverage, run lint/tooling/changed mutation checks, update docs and learnings, complete tasks and commit for independent review.

Independent case-position equivalence Should: preserve documented conservative parser policy, add unsupported-shape BLOCK and ordinary-case ALLOW controls; remove false equivalent marker after bounded red proof, run official targeted mutant, then request fresh exact-source review before full417 restart.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Recovered shared join used by preprocess, cmdparse case cut-short, require-review parse-failure net, enforce-pr-workflow fallback, and both attribution raw-text scans. Added exact joined-text heredoc boundary rows; isolated mutation checks kill both previous join survivors and the worktree case-comparison survivor. Node22 make lint and initial make tooling passed (839 gate rows, 118 tooling rows); final stable tooling rerun and changed mutation verification pending.

2026-10-03 independent Must: learning rename mutant label claimed dropping --find-renames but replacement explicitly forced --no-renames. Removed false equivalence and added unchanged-rename BLOCK paired with rename-plus-new-content ALLOW, preserving production hook. Official prior629 Linux run interrupted exit137; never pass evidence. Bounded red/green and official targeted mutant checks underway before new exact-source full417 validation.

Bounded Oct3 regression RED on explicit --no-renames:866passed/1failed, unchanged rename incorrectlyallowed while rename+extension allowed (/tmp/hooks-rename-red.exit contains 1). Production restored; official mutate.py --match learning-rename-detection targeted check baseline passes and mutant KILLED:1 mutants,0 problems,exit0 (/tmp/hooks-rename-official-targeted.log/.exit). Full417 exact-source run and task closure still pending.

Oct3 independent QA Should: case-position equivalent marker changed real protect-data-dir verdicts on benign unsupported syntax (no security bypass). Added data-only controls preserving spec08 conservative shape policy. Replacement RED:868passed/2failed, both unsupported shapes incorrectlyallowed, ordinary case ALLOW control passed (/tmp/hooks-case-red.log; /tmp/hooks-case-red.exit contains 1). Removed false marker and corrected label; production parser unchanged. Prior895 full run stopped only owned container,47kills/exit137 archived as interrupted diagnostic, never PASS. Official targeted mutant proof and fresh exact-source review/full417 pending.

Official GREEN after restoring unchanged production parser: mutate.py --match case-position replacement baseline passed, mutant KILLED;1 mutants,0problems,exit0 (/tmp/hooks-case-official-targeted.log/.exit). Syntax, shellcheck, learning-index and diff checks pass. Full417 and remaining task closure still pending new exact-source independent review.

Complete official make mutate-changed on reviewed source 9d035a1877e806e8ea11b5c9fde7ca3cc557812a: 417 mutants: 0 problem(s), exit 0; 413 killed and four independently audited equivalent survivors, no stale patterns. Raw /tmp/hooks-official-linux-9d.log, exact .head, .exit contains 0; post-run host/container tracked-byte hashes unchanged. Fresh Node22 make lint and make tooling both passed exit 0 (/tmp/hooks-lint-9d.log and /tmp/hooks-tooling-9d.log). Interrupted earlier runs remain diagnostic only. Final metadata commit gates and exact-head review follow.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Shared continuation joining now drives preprocess and raw scans, preserving single-quote/heredoc boundaries and conservative parse-failure refusal. Exact boundary controls, Linux case-comparison coverage, and corrected rename/case equivalence regressions are proven by complete official 417-mutant validation and make tooling, both exit 0.
<!-- SECTION:FINAL_SUMMARY:END -->
