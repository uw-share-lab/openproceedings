---
id: TASK-007
title: Add op eval near-miss and the error-code registry to spec 08
status: To Do
assignee: []
created_date: '2026-09-25 22:06'
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
- [ ] #1 op eval near-miss added to the CLI list
- [ ] #2 Error-code registry location decided (proposal: backend/src/openproceedings/diagnostics.py)
<!-- AC:END -->
