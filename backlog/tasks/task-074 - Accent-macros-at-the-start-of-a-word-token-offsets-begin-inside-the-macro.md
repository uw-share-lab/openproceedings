---
id: TASK-074
title: 'Accent macros at the start of a word: token offsets begin inside the macro'
status: To Do
assignee: []
created_date: '2026-09-26 21:07'
labels:
  - tokenizer
milestone: m-2
dependencies: []
ordinal: 73000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
task-027 review: tokenize's offsets for a word that begins with an accent macro start at the letter, not the macro: `\\"{O}del` gives the span `O}del` (3,8), an unbalanced brace; `\\v{S}ekar` likewise. Tokens are right; only offsets (so highlights) are off. Start the token at the macro's backslash.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Word-initial accent macros (\\" \\' \\v \\H …, braced and bare) give spans from the backslash to the word's end
- [ ] #2 Tokens unchanged: exhaustive suite and golden tokens; TOKENIZER_VERSION unchanged
<!-- AC:END -->
