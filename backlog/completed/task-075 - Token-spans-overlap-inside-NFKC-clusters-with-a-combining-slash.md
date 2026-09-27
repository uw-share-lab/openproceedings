---
id: TASK-075
title: Token spans overlap inside NFKC clusters with a combining slash
status: Done
assignee:
  - '@jeevan'
created_date: '2026-09-26 22:52'
updated_date: '2026-09-27 07:26'
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
- [x] #1 No two token spans overlap except pieces of one code point that share its span exactly
- [x] #2 Tokens unchanged (exhaustive suite); the overlap property's alphabet gains ½, ⑴ and U+0338
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Failing tests first: span goldens for slash clusters, overlap property alphabet gains the 1/2, parenthesized 1 and U+0338, and its exception becomes 'overlap is exactly one code point that folds to several pieces'. 2. Root cause in tokenize's slash-cluster branch. 3. Per-piece spans in _cluster_spans (offsets only; the fold is untouched, so tokens can't change). 4. Exhaustive suite, goldens, parity/differential, and a 300k differential against the pre-fix tokenizer.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
ID note: backlog 1.53 reuses the ids of archived tasks, so this task shares task-075 with the archived 'Warm search over wildcard phrases within the 100 ms page budget at 80k' (not reproduced; see task-031's notes). References to task-075 after 2026-09-26 18:55 mean this task.

Correction: the id note's time is 22:55 UTC (18:55 EDT).

Root cause: a U+0338 cluster (a character, then its combining marks) is NFKC'd whole so the slash composes, and tokenize gave EVERY folded piece the whole cluster's span (i, j). When the pieces land in different tokens (1/2 + slash -> 1, fraction slash, 2), x1 ended after the slash and 2y started at the 1/2, overlapping on two characters.
Fix: _cluster_spans gives each piece the raw characters it came from. Pieces before the last starter of the character's own NFKC form span the character alone. U+0345 (ypogegrammeni) is the only combining mark that folds to a non-mark, iota (checked over every code point), and the only one with ccc 240, so its iotas are the fold's last pieces; after a non-letter piece they start a word at the first raw U+0345, and the pieces before end there. The pieces themselves still come from the whole cluster's _fold, so tokens are unchanged by construction.
Found by a 300k differential against the pre-fix tokenizer, both pre-existing and inside slash clusters: (a) neq and the iota word both spanned the whole cluster (=, slash, U+0345; and the triple equals sign); (b) accent markup before a multi-piece character went to the first WORD piece even after operator/separator pieces, so the iota after \"-triple-integral-slash started before the ints (a start going backwards). Markup now belongs to the character's first piece only (task-074's rule: anything that starts no word forgets it).
Tests: 15 span goldens (test_slash_cluster_pieces_span_what_they_came_from); overlap property alphabet gains 1/2, parenthesized 1, U+0338 and U+0345, asserts monotone starts, and has 3 @examples. Mutants (per-piece spans off, iota split off, lead kept across op pieces): all killed by the goldens and by the property with its examples; without examples the ci profile (2,000) catches only the first, hence the examples.
Tokens unchanged: 300,000 texts (1,237 multi-piece code points with slash, U+0345 and other marks, TRICKY and LaTeX pieces, 20% wrapped in $...$) give identical token texts and op flags; 69,876 ends moved earlier (only off combining marks), 17,211 starts moved later (16,397 iota, 814 markup), zero overlaps other than one shared multi-piece code point, starts monotone. OP_EXHAUSTIVE=1 exhaustive suite: 1 passed. HYPOTHESIS_PROFILE=ci differential + parity + golden: 365 passed. Full uv run pytest: 2292 passed, 1 skipped (the exhaustive suite, run separately). make lint and make tooling green.
TOKENIZER_VERSION unchanged. The bump rule is about what inputs tokenize to, and token texts and op flags are identical. Offsets aren't in index_version (the index is fed the token texts joined by spaces) or in canonical_hash (canonical string + versions); they reach only highlights and AST/diagnostic spans. Same reasoning as task-074.
Docs: spec 02 §Token semantics, spec 03 §Highlights, token-contract skill, normalize.py docstring, learning addendum (2026-09-25 tokenizer entry).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Token spans inside a U+0338 cluster no longer overlap. The cluster is still folded whole, but _cluster_spans now gives each piece the raw characters it came from. Pieces before the last starter of the character's NFKC form span the character only (x1/2+slash+y: x1 (0,2), 2y (1,4), sharing just the 1/2). A U+0345 iota after a non-letter piece starts at its own mark. Accent markup before a multi-piece character goes to its first piece only (a start went backwards). The last two cases were pre-existing and were found by a 300k differential. Tokens unchanged: 300k-text differential vs the pre-fix tokenizer (identical token texts and op flags), OP_EXHAUSTIVE=1 suite passed, ci-profile differential+parity+golden 365 passed, full suite 2292 passed. TOKENIZER_VERSION unchanged: offsets aren't in index_version or canonical_hash. 15 span goldens; the overlap property's alphabet gains 1/2, parenthesized 1, U+0338 and U+0345, with 3 @examples and a monotone-start check.
<!-- SECTION:FINAL_SUMMARY:END -->
