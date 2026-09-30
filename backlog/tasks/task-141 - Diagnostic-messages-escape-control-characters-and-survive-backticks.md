---
id: TASK-141
title: Diagnostic messages escape control characters and survive backticks
status: To Do
assignee:
  - '@jeevanp03'
created_date: '2026-09-30 04:30'
labels:
  - query
milestone: m-3
dependencies: []
ordinal: 123000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by TASK-140's review (2026-09-30). diagnostics.clip() quotes query text raw, so a newline, tab, NUL, ESC or U+2028 typed in a query ends up in a diagnostic message (more often since TASK-140 quotes whole levels). Nothing breaks today (logs record codes only; JSON escapes; the UI renders plain text), but messages should be safe to log and copy. A backtick in the query also breaks the message's backtick quoting.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 clip() collapses whitespace runs to one space and escapes control characters; every diagnostic quoting query text goes through it
- [ ] #2 A backtick inside a quoted span doesn't break the quoting (escape or choose a different delimiter), documented in the error-diagnostics skill
- [ ] #3 Parser goldens and a property pin it
<!-- AC:END -->
