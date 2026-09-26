---
id: TASK-010
title: Implement normalize.py and the golden token table
status: Done
assignee:
  - '@jeevanp03'
created_date: '2026-09-26 01:06'
updated_date: '2026-09-26 01:54'
labels:
  - query
milestone: m-1
dependencies:
  - TASK-009
ordinal: 9000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The token contract (spec 02 §Token semantics; token-contract skill), with an offset map for highlights.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Golden token table has ≥100 cases incl. Unicode dashes, ligatures, LaTeX, digits, ß
- [x] #2 No stemming, stopwords or synonyms anywhere (exactness-guardian review)
- [x] #3 TOKENIZER_VERSION defined in normalize.py (folding it into canonical_hash is task-013 AC #3)
- [x] #4 tokenize(text) returns tokens with half-open raw code-point spans; normalize(text) returns the token strings
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
TDD: golden token table (>=100 cases) first, then normalize() + offset map; TOKENIZER_VERSION folded into canonical_hash later (task-013). Pure function, no deps beyond stdlib unicodedata.
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
normalize.py is the single token contract (spec 02 §Token semantics): NFKC, casefold, script-aware mark fold (Latin/Greek/Cyrillic/Hebrew/Arabic/digit bases fold; Cyrillic breve, Arabic hamza, Thai, kana and Indic marks kept), a three-state LaTeX mask (Pandoc $…$ rule, $$…$$, \(…\), \[…\], accent macros incl. {\i}, \- joins), invisible characters join and U+2061–2064 separate. tokenize() returns Token(text,start,end) with raw half-open spans; normalize() returns strings. TOKENIZER_VERSION = "1". Evidence: 190+ golden rows; a Hypothesis property against an independent block-range reference; a nightly exhaustive check of every code point in 8 contexts (0 divergences); the exactness reviewer's mutants all killed after round 3. Known limits (CJK runs are one token; accents and vowel points fold) are in spec 02.
<!-- SECTION:FINAL_SUMMARY:END -->
