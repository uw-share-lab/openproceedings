---
id: TASK-007
title: Add op eval near-miss and the error-code registry to spec 08
status: Done
assignee: []
created_date: '2026-09-25 22:06'
updated_date: '2026-09-25 22:26'
labels:
  - ops
dependencies: []
references:
  - .claude/skills/error-diagnostics/SKILL.md
ordinal: 7000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The near-miss-evaluator (recall@25, spec 06) and error-diagnostics skill assume a CLI subcommand and a registry file that spec 08 does not list.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 op eval near-miss added to the CLI list
- [x] #2 Error-code registry location decided (proposal: backend/src/openproceedings/diagnostics.py)
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Spec 08 now lists `op eval near-miss` (06 recall@25) in the CLI table, and fixes the error-code registry at backend/src/openproceedings/diagnostics.py (layout block). Done in the chore/claude-tooling review round.
<!-- SECTION:FINAL_SUMMARY:END -->
