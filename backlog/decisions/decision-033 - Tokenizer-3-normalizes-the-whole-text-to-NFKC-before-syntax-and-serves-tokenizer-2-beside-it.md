---
id: decision-033
title: >-
  Tokenizer 3 normalizes the whole text to NFKC before syntax and serves
  tokenizer 2 beside it
date: '2026-10-03 02:46'
status: accepted
---
## Context

Tokenizer 2 reads LaTeX syntax before normalizing individual characters. NFC, NFD, NFKC and NFKD forms of the same text can consequently produce different tokens, violating the exact token contract. Normalizing to NFC first still misses compatibility characters; translating only full-width delimiters still leaves adjacent compatibility spaces and digits affecting syntax. Whole-text NFKC before every syntax step makes the contract form-independent.

Changing the tokenizer silently would strand records pinned to existing indexes. The alternative is a versioned tokenizer boundary, with frozen tokenizer 2 retained and every query reader selecting the index's version. Synthetic form properties and versioned lexer goldens demonstrate changed cases; the historical local 95,877-record delta and 14-record replay in `docs/results/2026-10-02-tokenizer-3.md` found zero corpus token changes and zero membership changes, which does not remove the need for a version bump.

## Decision

Tokenizer 3 normalizes the whole text to NFKC before reading syntax, retaining raw offsets for diagnostics and highlighting. Serve tokenizer 2 and 3 independently of index schema 2 and 3; choose the target index before semantic query validation and use its tokenizer throughout parsing, aliases, filter edits, hashing, highlighting and replay.

## Consequences

The tokenizer version remains an `index_version` and `canonical_hash` input. Existing records reproduce on their tokenizer-2 pins; replay against only a tokenizer-3 index reports drift even if the ID set is unchanged. Raw query length and basic argument checks precede index I/O; unavailable pins precede tokenizer-dependent semantic errors. The frontend editor follows `/meta.tokenizer_version`, defaulting to 3 when metadata is missing or unsupported.

Specs 02–05 and 08, the token-contract, query-grammar, index-versioning and codemirror-lezer skills, versioned engine/query tests and generated frontend goldens describe this boundary. Independent schema/tokenizer build parameters and compatibility tables must remain separate. Dedup title-key normalization (decision-031) and twin takedown behavior (decision-032) retain their own semantics. Retire tokenizer 2 only when no retained record requires a tokenizer-2 index; revisit the normalization choice only with a new version and reproducibility evidence.
