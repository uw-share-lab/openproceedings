---
id: TASK-070
title: 'Make the tokenizer''s LaTeX scan linear for unclosed $ \( \[ openers'
status: Done
assignee: []
created_date: '2026-09-26 06:11'
updated_date: '2026-09-26 21:04'
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

Review (APPROVE; 0 mismatches over ~2M adversarial texts incl. every string up to length 6 over the LaTeX alphabet) fixes: the timing test is a doubling ratio (tokenize at 2k vs 8k chars < 8x; quadratic is ~16x) plus the parse bound at the cap, so it's machine-independent and the old scan fails it in ~11 s total (was minutes); the $$1 case is dropped and the title corrected ($$ was never quadratic: it closes at the next $$); the Pandoc dollar table has its own attribute, so find(…, "$") can't collide with it. Rejected: a compact array('i') table (peak 1.9 MB at 40k chars; abstracts are far shorter).

Verification (APPROVE; 400k-text differential 0 mismatches; 35 serial + 45 parallel runs green; old scan fails all 3 at ~16x in 11 s). Nits fixed: fastest() takes the best of 9 runs (0/60 failures under a 12-process CPU hog, vs 2/60 at best of 3). Correction to the first note: the timing test is now a quadrupling ratio (tokenize at 2k vs 8k chars < 8x) plus the parse bound at the 2,000-char cap; the 40,000-char bound and the $$1 case are gone.
<!-- SECTION:NOTES:END -->
