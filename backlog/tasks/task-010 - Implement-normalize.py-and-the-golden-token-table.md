---
id: TASK-010
title: Implement normalize.py and the golden token table
status: In Progress
assignee:
  - '@jeevanp03'
created_date: '2026-09-26 01:06'
updated_date: '2026-09-26 01:40'
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
- [ ] #1 Golden token table has ≥100 cases incl. Unicode dashes, ligatures, LaTeX, digits, ß
- [ ] #2 No stemming, stopwords or synonyms anywhere (exactness-guardian review)
- [ ] #3 TOKENIZER_VERSION defined in normalize.py (folding it into canonical_hash is task-013 AC #3)
- [ ] #4 tokenize(text) returns tokens with half-open raw code-point spans; normalize(text) returns the token strings
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
TDD: golden token table (>=100 cases) first, then normalize() + offset map; TOKENIZER_VERSION folded into canonical_hash later (task-013). Pure function, no deps beyond stdlib unicodedata.
<!-- SECTION:PLAN:END -->
