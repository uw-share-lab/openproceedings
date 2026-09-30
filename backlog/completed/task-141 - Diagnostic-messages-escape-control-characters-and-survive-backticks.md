---
id: TASK-141
title: Diagnostic messages escape control characters and survive backticks
status: Done
assignee:
  - '@jeevanp03'
created_date: '2026-09-30 04:30'
updated_date: '2026-09-30 05:25'
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
- [x] #1 clip() collapses whitespace runs to one space and escapes control characters; every diagnostic quoting query text goes through it
- [x] #2 A backtick inside a quoted span doesn't break the quoting (escape or choose a different delimiter), documented in the error-diagnostics skill
- [x] #3 Parser goldens and a property pin it
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Failing tests: clip unit table + property (test_diagnostics), parser goldens QUOTED (test_parser), parse property with hostile characters (test_properties).
2. clip(): collapse whitespace runs (re \s = str.isspace) to one space; escape backtick and Cc/Cf/Cs as Python escapes; truncate without splitting an escape.
3. Route remaining raw quotes through clip (lexer unterminated phrase, raw[s], raw[0], quote char; reference engine wildcard).
4. Document in error-diagnostics skill and spec 02; message text is prose, not API contract.
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
diagnostics.clip() now returns quoted query text as one line of visible characters: whitespace runs (exactly str.isspace, as the lexer splits) collapse to one space, and a backtick or a Cc/Cf/Cs character is written as its Python escape (`\x60`, `\x00`, `\u202e`), so a backtick can't end the message's backtick quoting (the UI's Coded/Ticked pair backticks). Shortening counts escapes whole. Five quotes that bypassed clip (unterminated phrase q[i:i+20], stray wildcard raw[s], lookalike minus raw[0], ambiguous quote q[k], reference engine wildcard cap) now use it. Backslashes stay raw (LaTeX); the span is the exact locator. Message text is prose, not API contract, so no OpenAPI change. Tests: clip table + property (test_diagnostics), QUOTED parser goldens (test_parser), property over queries seeded with hostile characters in both modes (test_properties). Documented in the error-diagnostics skill and spec 02.
<!-- SECTION:FINAL_SUMMARY:END -->
