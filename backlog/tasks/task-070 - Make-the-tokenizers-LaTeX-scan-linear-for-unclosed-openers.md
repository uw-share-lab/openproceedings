---
id: TASK-070
title: 'Make the tokenizer''s LaTeX scan linear for unclosed \( \[ $$ openers'
status: To Do
assignee: []
created_date: '2026-09-26 06:11'
updated_date: '2026-09-26 06:27'
labels:
  - query
  - performance
milestone: m-2
dependencies: []
ordinal: 69000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
M1 gate verification: normalize._latex_mask scans to the end of the text for every unclosed opener (_find_closing_dollar for a $ that never closes, e.g. $ followed by a digit; _find for \( and \[), so the tokenizer is quadratic on such text. Worst measured at the 2,000-character query cap: '$1' repeated, 0.56-0.78 s; an unbroken run of '\(', 0.21-0.36 s (bounded; abstracts are short). Precompute the next closer per position (backslash-run parity from the run start) so the scan is linear. Deferred from the M1 gate because it changes tokenizer internals: it must not change a single token.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Tokenize output unchanged for every code point (OP_EXHAUSTIVE=1) and on the golden and property suites; TOKENIZER_VERSION unchanged
- [ ] #2 parse('$1' * 1000), parse('\\(' * 1000) and tokenize of the same texts are linear (timing test)
<!-- AC:END -->
