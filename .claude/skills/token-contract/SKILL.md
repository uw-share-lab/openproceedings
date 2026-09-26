---
name: token-contract
description: The exact normalization contract shared by the query parser and the index (NFKC, case-fold, diacritic fold, LaTeX handling, split on non-alphanumerics, and nothing else), the golden cases that pin it, and the TOKENIZER_VERSION bump rule. Use when writing or reviewing normalize.py, the Tantivy analyzer, highlighting, or anything that decides what a "word" is.
---

# Token contract (spec 02 §Token semantics)

## The pipeline — in this order, and nothing else
1. Unicode **NFKC** (`ﬁ` → `fi`, full-width → ASCII forms).
2. **Case-fold** (`str.casefold()`, not `lower()` — `ß` → `ss`).
3. **Mark fold**: NFD, drop combining marks (combining class ≠ 0) whose base letter is Latin, Greek,
   Cyrillic, Hebrew or Arabic (`naïve` → `naive`, `שָׁלוֹם` → `שלום`); **keep** marks that spell a different
   word (Thai tones, kana voicing, Indic signs); drop a stray mark with no base; then NFC to recompose.
   The base letter carries across raw characters, so a decomposed `e` + U+0301 folds like `é`.
4. **LaTeX** (by classifying characters, so offsets survive): `\cmd{X}` → `X`; a bare `\cmd` outside
   math is dropped; inside math `$…$` a command name is a word (`$\epsilon$` → `epsilon`); `\%` `\&` `\$`
   `\\` are separators; neither `\$` nor a `$` followed by a digit (currency) opens math.
5. **Split** on every char that is not a Unicode letter, digit or non-combining mark. Positions are
   consecutive across the split (`vision-language` → `vision`@0 `language`@1). All Unicode format characters
   (category Cf: soft hyphen, ZWSP, ZWJ, ZWNJ, direction marks, BOM) **join**: `bench\u00admark` → `benchmark`.

Known limits (CJK runs are one token; Hebrew/Arabic points fold) are listed in spec 02 §Known limits.

**Never:** stemming, lemmatization, stopword removal, synonyms, spelling correction, n-grams, compound
splitting beyond punctuation, number normalization (`GPT-4` stays `gpt` `4`).

## Single source of truth
`backend/src/openproceedings/query/normalize.py` is the only implementation: `tokenize(text) ->
list[Token]` (each with the raw half-open code-point span it came from, for highlights) and
`normalize(text) -> list[str]`. It works character by character; a Hypothesis property pins it equal to
the simple whole-string definition, including an adversarial Unicode alphabet, at 50k examples nightly. The index is fed its output joined by spaces, and the Tantivy analyzer only splits on
whitespace + lowercases (a no-op on normalized input). Any second implementation — in the frontend
highlighter, a script, a test helper — is a bug; import or call the API instead.

## Golden cases (tests in `backend/tests/golden/test_tokens.py`)
| Input | Tokens |
|---|---|
| `Benchmarking LLMs` | `benchmarking`, `llms` |
| `Trust-aware` | `trust`, `aware` |
| `Vision–Language` (en dash) | `vision`, `language` |
| `naïve Bayes` | `naive`, `bayes` |
| `GPT-4o` | `gpt`, `4o` |
| `model's` | `model`, `s` |
| `$\epsilon$-DP` | `epsilon`, `dp` |
| `\textit{TrustLLM}` | `trustllm` |
| `ﬁne-tuning` (ligature) | `fine`, `tuning` |
| `STRASSE` / `Straße` | `strasse` / `strasse` |
Add a row for every bug ever found; never delete one.

## TOKENIZER_VERSION bump rule
Bump when **any** input could tokenize differently than before — even if no golden case changes. The
version is folded into `index_version` and `canonical_hash`, so old search records correctly report
`drifted` instead of falsely claiming `reproduced`. Refactors proven token-identical by the full-corpus
parity test do not bump.

## Checklist for a change here
- [ ] golden table extended with the case that motivated the change
- [ ] `TOKENIZER_VERSION` bumped (or parity run proves no change)
- [ ] tokenizer-parity + differential suites green
- [ ] `exactness-guardian` review (routed automatically by `/review-gate`)
