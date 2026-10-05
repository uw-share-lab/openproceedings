---
id: decision-044
title: >-
  A control character in an abstract is replaced by one space at import, as in
  titles; a snapshot change, not a tokenizer bump (TASK-188)
date: '2026-10-05 23:59'
status: accepted
---
## Context

decision-036 replaces a control character in an OpenReview title by one space at import and left abstracts to
TASK-188. On snapshot `2026-10-05-10b5a205a63f` (133,629 records), 59 abstracts hold 117 non-whitespace control
characters: U+0002 ×106, U+000F ×6, U+0008 ×4, U+0000 ×1. 98 sit between two letters where a line-break hyphen
was (`quanti␂fying`); the rest stand for a character the PDF lost (U+0002 for `×`, U+000F for `ε`), so neither a
space nor deletion restores the text. Options: (a) one space, as in titles; (b) delete every one; (c) a rule per
character or context (delete U+0002 between letters, map U+000F to `ε`). (b) and (c) mend the 98 line breaks
but can fuse a real hyphen (decision-036's `state␂of-the-art`) and change those records' tokens.

## Decision

The project owner chose (2026-10-05) (a): at import, each control character in an abstract (Unicode category
Cc, other than the whitespace characters already normalised) is replaced by one space, by the same rule
decision-036 applies to titles. The tokenizer already splits on these characters, so no token changes and
`TOKENIZER_VERSION` is not bumped; the stored text and content hashes of the affected records change in the
next snapshot.

## Consequences

- The next snapshot's diff lists the 59 records as changed text; their tokens, and so every search result,
  are unchanged.
- A search for the whole word (`quantifying`) still misses the papers whose abstract has a line-break control
  character inside it; that is a property of the source text, stated in spec 01.
- Authors are out of scope, as in decision-036 (one author name holds U+007F).

