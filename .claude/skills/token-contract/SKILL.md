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
   Arabic hamza, Thai tones, kana voicing, Indic signs); drop a stray combining mark (class ≠ 0) with no base; then NFC.
   A class-0 mark (an Indic vowel sign such as U+0CE2) is a word character even with no base: a word made only
   of marks makes no token, but a letter after it joins it (U+0CE2 alone → nothing, U+0CE2 + `x` → one word).
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
is its name; markup that opens a word (an accent macro such as `\"{O}del` or `\v{S}`, `\-`, or a math
`^`/`_`: `$^2x$` spans `^2x`) starts the span at its first character,
task-074; two spans overlap only on exactly one code point that folds to several pieces, `½` → `1`, `2`:
inside a U+0338 cluster each piece spans the raw characters it came from, except that pieces before the first
raw U+0345 end at it even if a later mark belongs to them, task-075; a Token is text, span and `op` only,
since task-075's `reach` was retired after decision-008; no span decides what parses: the lexer's detached-wildcard check reads
the folded pieces after the last word, `tokenize_with_tail(text) -> (tokens, Tail)`, decision-008) and
`normalize(text) -> list[str]`. It works character by character (with two exact shortcuts, task-073: a whole
text that is ASCII with no `\` or `$` is its lower-cased `[A-Za-z0-9]+` runs, and in the loop an ASCII
character with no mark after it skips `_fold`; `test_highlight_speed.py` pins both to a frozen copy of the
loop, `tests/unit/tokenize_before.py`; and three more, TASK-088: a text with no `\` or `$` skips the LaTeX
mask, the loop takes a stretch of KEEP ASCII characters with no mark after it word by word, and `_fold_char`
folds a raw character once per process when its fold is the same after a base of each class `_folds_marks`
tells apart (`_BASES`; a bounded table, `_FOLDED`), all pinned, with the `Tail`, to a frozen copy of the loop
before them, `tests/unit/tokenize_before_088.py`, and `test_normalize.py` checks every ASCII character alone and in
`a?b` against the loop, and that no operator or letter look-alike key is ASCII); a Hypothesis property pins it equal to an
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
