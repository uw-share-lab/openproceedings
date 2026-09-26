---
id: TASK-070
title: 'Make the tokenizer''s LaTeX scan linear for unclosed \( \[ $$ openers'
status: To Do
assignee: []
created_date: '2026-09-26 06:11'
labels:
  - query
  - performance
milestone: m-2
dependencies: []
ordinal: 69000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
M1 gate (security/QA re-review): normalize._latex_mask calls _find/_find_closing_dollar to the end of the text for every unclosed opener, so a single run of '\(' repeated costs ~0.36 s at the 2,000-character query cap (bounded; abstracts are short). Precompute the next unescaped closer per position (backslash-run parity from the run start) so the scan is linear. Deferred from the M1 gate because it changes tokenizer internals: it must not change a single token.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Tokenize output unchanged for every code point (OP_EXHAUSTIVE=1) and on the golden and property suites; TOKENIZER_VERSION unchanged
- [ ] #2 parse(('\\('*1000)) and tokenize of the same text are linear (timing test)
<!-- AC:END -->
