---
id: TASK-010
title: Implement normalize.py and the golden token table
status: To Do
assignee: []
created_date: '2026-09-26 01:06'
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
- [ ] #1 normalize(text) returns tokens and a raw↔normalized code-point offset map
- [ ] #2 Golden token table has ≥100 cases incl. Unicode dashes, ligatures, LaTeX, digits, ß
- [ ] #3 TOKENIZER_VERSION defined and folded into canonical_hash
- [ ] #4 No stemming, stopwords or synonyms anywhere (exactness-guardian review)
<!-- AC:END -->
