---
id: TASK-248
title: >-
  cmdparse strips more command wrappers (xcrun, caffeinate, arch, doas, flock,
  unbuffer)
status: To Do
assignee: []
created_date: '2026-10-14 16:32'
updated_date: '2026-10-14 16:43'
labels:
  - tooling
dependencies: []
priority: low
ordinal: 174000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-244's security review found that git run behind a wrapper cmdparse doesn't strip (xcrun git restore backlog/..., caffeinate, arch, doas, flock, unbuffer) reaches every gate that uses cmdparse as an unknown command: protect-data-dir, enforce-pr-workflow, require-review and block-ai-attribution all miss it (xcrun git commit -m ... reaches the attribution gate unstripped too). cmdparse.WRAPPERS / WRAPPER_VALUE_OPTS list env, nice, timeout and others but not these. Today this sits under protect-data-dir's documented limitation (obfuscated commands may bypass).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Each listed wrapper is stripped by cmdparse before every gate reads the command, with its value-taking options and its non-option arguments (flock's lock file and its -c '<cmd>' string, arch -arch <a>)
- [ ] #2 Case-table rows in each gate's table and mutants in .claude/scripts/mutants/gates.json cover them
<!-- AC:END -->
