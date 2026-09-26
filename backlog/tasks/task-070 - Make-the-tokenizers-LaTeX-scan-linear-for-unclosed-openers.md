---
id: TASK-070
title: 'Make the tokenizer''s LaTeX scan linear for unclosed \( \[ $$ openers'
status: In Progress
assignee: []
created_date: '2026-09-26 06:11'
updated_date: '2026-09-26 20:43'
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
- [x] #1 Tokenize output unchanged for every code point (OP_EXHAUSTIVE=1) and on the golden and property suites; TOKENIZER_VERSION unchanged
- [x] #2 parse('$1' * 1000), parse('\\(' * 1000) and tokenize of the same texts are linear (timing test)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented normalize._Closers: _find and _find_closing_dollar answered for every start from one right-to-left pass per closer (built lazily, only when an opener needs it); _latex_mask uses it. The old scans stay for first_math_end (a single scan) and as the property test's oracle. TOKENIZER_VERSION unchanged. Checked: a Hypothesis property that tables == scans for every start; OP_EXHAUSTIVE=1 passes; a one-off differential of the previous normalize.py vs the new one on 300,000 random LaTeX-heavy texts + the 200-record fixture gave identical tokens; timing test (parse at the 2,000-char cap < 0.25 s, tokenize at 40,000 chars < 2 s for $1, \(, \[, $$1) fails on the old scan. Mutants 7/8 killed; the survivor (start < n-1 guard) is equivalent because every closer is two characters.
<!-- SECTION:NOTES:END -->
