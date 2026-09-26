---
id: TASK-074
title: 'Accent macros at the start of a word: token offsets begin inside the macro'
status: Done
assignee: []
created_date: '2026-09-26 21:07'
updated_date: '2026-09-26 22:52'
labels:
  - tokenizer
milestone: m-2
dependencies: []
ordinal: 73000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
task-027 review: tokenize's offsets for a word that begins with an accent macro start at the letter, not the macro: in the raw text G-backslash-quote-brace-O-brace-del (a BibTeX umlaut before a capital O), the span is "O}del" (3,8), an unbalanced brace; the v-caron macro before S (Sekar) likewise. Tokens are right; only offsets (so highlights) are off. Start the token at the macro's backslash.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Word-initial accent macros (\\" \\' \\v \\H …, braced and bare) give spans from the backslash to the word's end
- [x] #2 Tokens unchanged: exhaustive suite and golden tokens; TOKENIZER_VERSION unchanged
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented in tokenize: a run of JOIN markup (accent macros, \\-) seen while no word is open is remembered, and the word that starts next starts its span there; a separator, a math command, or any character that starts no word forgets it. Tokens unchanged: exhaustive suite (OP_EXHAUSTIVE=1), golden tokens, highlights; a 300,000-text differential against the previous tokenizer gives identical token texts, ends and op flags, with 36,021 starts moved earlier and every moved-over character JOIN (or the backslash of a following math command, \\-\\alpha). TOKENIZER_VERSION unchanged (offsets aren't part of the token contract's output). Goldens: \\"{O}del (0,8), \\v{S}ekar (0,9), after a space, \\'{E}cole and \\H{O}, \\"{\\i}ve, and unchanged in-word and \\- cases. Docs: token-contract skill, highlight.py docstring, spec 03 §Highlights.

Review fix (must): an operator command's name chars (JOIN) set the lead, so the word after \\leq, \\times, \\neq, \\not= started inside the operator's name ($n\\leq5$ gave 5 the span leq5, also Term spans in the parser). tokenize now skips an operator command's name (i = cmd_end); goldens for $n\\leq5$, $\\neq1$, $\\not=x$, $3\\times10^5$; a Hypothesis property (LaTeX-heavy alphabet) that spans are in bounds and never overlap, except pieces of one non-ASCII code point that folds to several, fails on the unfixed code. Exhaustive suite passes; against the pre-task-074 tokenizer, 300,000 texts give identical tokens and starts that only move earlier. \\"{}x keeps x's own span: the empty group is a separator, so there is no markup to join (noted, as the reviewer suggested).

Verification (APPROVE; 171 overlaps -> 0 over 300k texts, tokens identical, no start later; operator edge cases and parser Term spans correct) nits: the overlap property wraps half its texts in $…$ so operators are reached under the dev profile, and its comment now says exactly what the shared-span exception covers (a combining-slash cluster like x½̸y overlapping by two characters predates task-074 and is out of its scope).
<!-- SECTION:NOTES:END -->
