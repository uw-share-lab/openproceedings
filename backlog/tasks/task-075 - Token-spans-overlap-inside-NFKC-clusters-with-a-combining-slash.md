---
id: TASK-075
title: Token spans overlap inside NFKC clusters with a combining slash
status: To Do
assignee: []
created_date: '2026-09-26 22:52'
labels:
  - tokenizer
milestone: m-3
dependencies: []
ordinal: 73000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
task-074 verification: a code point that folds to several pieces, clustered with U+0338 (x½̸y), gives tokens whose spans overlap by two characters (x1 (0,3), 2y (1,4)). Tokens are right; only offsets (highlights) are off. Predates task-074.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 No two token spans overlap except pieces of one code point that share its span exactly
- [ ] #2 Tokens unchanged (exhaustive suite); the overlap property's alphabet gains ½, ⑴ and U+0338
<!-- AC:END -->
