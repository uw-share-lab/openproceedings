---
id: TASK-169
title: >-
  Hook test harness: hostile probes stay data, never reach an executed shell
  (2026-10-02 incident)
status: Done
assignee:
  - '@jeevanparmar'
created_date: '2026-10-02 09:27'
updated_date: '2026-10-02 20:53'
labels:
  - security
  - tooling
  - tests
dependencies: []
references:
  - .claude/hooks/tests/test-openproceedings-gates.sh
  - .claude/hooks/lib/cmdparse.py
priority: medium
ordinal: 139000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Source: incident on 2026-10-02. A reviewer agent probing a guard hook wrote its probe in a heredoc that closed early, so the shell ran the probe's own `rm -rf data` in the home directory. Hook probes are hostile strings by design. The case tables already pass most probes as argv (`payload_bash`/`payload_at` in test-openproceedings-gates.sh build the hook's JSON in Python). Two risks remain: a row whose probe is written in double quotes with an unescaped `$(` or backtick, which bash expands while the table runs, and reviewers' ad hoc probes outside the tables. Close both: probes live as data (single-quoted, or read from a data file), a lint catches the unsafe form, and the reviewer guidance says how to probe safely.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Every case-table probe reaches the hook only as data (argv to a Python helper, or a data file), and a lint or case-table row fails on a payload_* argument in double quotes containing an unescaped `$(` or backtick
- [x] #2 A documented helper (for example a Python entry point taking the probe from a file or argv) lets a reviewer feed one probe to a hook or to cmdparse without a shell; real execution, when needed, runs only in a mktemp sandbox with HOME and the working directory set to it
- [x] #3 The security-reviewer and qa-auditor agents and the review-gates skill tell reviewers to probe hooks only that way
- [x] #4 A learnings entry records the 2026-10-02 incident and the rule (via /record-learnings)
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Preserve recovered implementation; reproduce regressions, scan sed script files, add deterministic join and case-folding coverage, run lint/tooling/changed mutation checks, update docs and learnings, complete tasks and commit for independent review.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Recovered probe helper/lint, fixture coverage and reviewer guidance. make tooling passes including118 tooling rows; incident documented in2026-10-02-hook-probes-must-remain-data.md and index regenerated. Explicit no-subagent recovery instruction requires recording learning directly rather than spawning learning-recorder.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Recovered safe probe helper and case-table expansion lint, fixtures, reviewer guidance, and incident learning. make tooling passed with118 tooling rows; helper tests prove hook/cmdparse data input and disposable sandbox behavior. Node22 lint passed. No hostile probe was executed during recovery.
<!-- SECTION:FINAL_SUMMARY:END -->
