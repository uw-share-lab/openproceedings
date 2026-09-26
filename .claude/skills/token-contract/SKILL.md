---
name: token-contract
description: The exact normalization contract shared by the query parser and the index (NFKC, case-fold, diacritic fold, LaTeX handling, split on non-alphanumerics, and nothing else), the golden cases that pin it, and the TOKENIZER_VERSION bump rule. Use when writing or reviewing normalize.py, the Tantivy analyzer, highlighting, or anything that decides what a "word" is.
---

# Token contract (spec 02 §Token semantics)

## The pipeline — in this order, and nothing else
1. Unicode **NFKC** (`ﬁ` → `fi`, full-width → ASCII forms).
2. **Case-fold** (`str.casefold()`, not `lower()` — `ß` → `ss`).
3. **Mark fold**: NFD, drop combining marks (combining class ≠ 0) whose base's Unicode NAME begins with
   LATIN, GREEK, CYRILLIC, HEBREW, ARABIC or EXTENDED ARABIC, or is an ASCII digit; **keep** marks that spell a distinct letter (Cyrillic breve,
   Arabic hamza, Thai tones, kana voicing, Indic signs); drop a stray mark with no base and any mark-only run; then NFC.
4. **LaTeX** (a three-state mask — keep / separate / join — so offsets survive): `\cmd{X}` → `X`; a bare
   `\cmd` outside math is dropped; math is `$…$` (Pandoc rule: opener followed by a non-space, closer
   preceded by a non-space and not followed by a digit), `$$…$$`, `\(…\)`, `\[…\]`, and inside it a
   command name is a word — except math with a Unicode spelling (decision-006, `query/mathsyms.py`): a
   Greek command is its letter (`$\alpha$` → `α`), an operator command its operator's name (`$\le$` →
   `leq`, `\not\in` → `notin`), and `^`/`_` join one ASCII letter/digit or a braced run of them (`$n^2$` →
   `n2`); a fourth mask state, SUB, marks those commands, and a Greek letter right after another command's
   name starts a new word (`\hat\theta` → `hat θ`); accent macros (`\"o`, `\H{o}`, `\"{\i}`) and `\-` join the word; `\%` `\&` `\$` `\\`
   separate. The scan is linear (task-070): each opener's closer comes from a table built in one right-to-left
   pass (`_Closers`), so an opener that never closes costs a lookup, not a scan to the end of the text.
5. **Split** on every char that is not a Unicode letter, digit or non-combining mark; a Unicode operator
   in `mathsyms.OPERATORS`, looked up **after NFKC** (so `∬` → `int int`, `𝛁` → `nabla`, `ŀ` → `l cdot`), is
   a token of its own, its LaTeX name (`×` → `times`); a U+0338 slash composes with the character before
   it (`∈`+U+0338 → `∉` → `notin`); `∆` is read as `Δ`. Invisible characters
   **join** (Cf, variation selectors, enclosing marks, CGJ); the invisible math operators U+2061–2064
   **separate**.

Known limits (CJK runs are one token; Hebrew/Arabic points fold) are listed in spec 02 §Known limits.

**Never:** stemming, lemmatization, stopword removal, synonyms, spelling correction, n-grams, compound
splitting beyond punctuation, number normalization (`GPT-4` stays `gpt` `4`).

## Single source of truth
`backend/src/openproceedings/query/normalize.py` is the only implementation: `tokenize(text) ->
list[Token]` (each with the raw half-open code-point span it came from, for highlights: a math command's span
is its name; markup that opens a word, such as `\"{O}del` or `\v{S}`, starts the span at its backslash,
task-074) and
`normalize(text) -> list[str]`. It works character by character; a Hypothesis property pins it equal to an
independent whole-string definition (block ranges, not Unicode names), including an adversarial Unicode
alphabet, and the nightly workflow checks every code point in 8 contexts (`OP_EXHAUSTIVE=1`). The index is fed its output joined by spaces, and the Tantivy analyzer only splits on
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
| `$\epsilon$-DP` | `ε`, `dp` (tokenizer 2; `epsilon` in 1) |
| `$\hat\theta$` | `hat`, `θ` (a Greek letter after another command's name starts a word) |
| `∈` + U+0338 (a decomposed `∉`) | `notin` (NFKC before the operator table, never `in`) |
| `5×3`, `$5 \times 3$` | `5`, `times`, `3` |
| `O(n²)`, `$O(n^2)$` | `o`, `n2` |
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
