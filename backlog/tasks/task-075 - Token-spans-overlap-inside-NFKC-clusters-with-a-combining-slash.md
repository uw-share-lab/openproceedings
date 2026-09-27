---
id: TASK-075
title: Token spans overlap inside NFKC clusters with a combining slash
status: To Do
assignee: []
created_date: '2026-09-26 22:52'
updated_date: '2026-09-26 23:31'
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

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
ID note: backlog 1.53 reuses the ids of archived tasks, so this task shares task-075 with the archived 'Warm search over wildcard phrases within the 100 ms page budget at 80k' (not reproduced; see task-031's notes). References to task-075 after 2026-09-26 18:55 mean this task.

Correction: the id note's time is 22:55 UTC (18:55 EDT).
<!-- SECTION:NOTES:END -->
