---
id: TASK-029
title: Tokenizer parity test over the full corpus
status: To Do
assignee: []
created_date: '2026-09-26 01:06'
labels:
  - engine
milestone: m-2
dependencies:
  - TASK-023
ordinal: 28000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Index tokens == normalize.py tokens for every record (spec 03 §Tokenizer).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 0 diffs on the Trust-Evals snapshot
- [ ] #2 Fails loudly with the first differing record and token
<!-- AC:END -->
