---
name: token-contract
description: The exact normalization contract shared by the query parser and the index (NFKC, case-fold, diacritic fold, LaTeX handling, split on non-alphanumerics, and nothing else), the golden cases that pin it, and the TOKENIZER_VERSION bump rule. Use when writing or reviewing normalize.py, the Tantivy analyzer, highlighting, or anything that decides what a "word" is.
---

# Token contract (spec 02 §Token semantics)

## The pipeline — in this order, and nothing else
1. Unicode **NFKC** (`ﬁ` → `fi`, full-width → ASCII forms), of the **whole text, before any other step reads it**
   (tokenizer 3, decision-033). So a text and its NFC, NFD, NFKC and NFKD forms give the same tokens: `Caf\é`
   is `caf`, `e` whether the `é` is one code point or `e` + U+0301, and full-width `＄`/`＼` (and small `﹩`/`﹨`)
   are `$`/`\`, so LaTeX. Tokenizer 2 ran NFKC one raw character at a time *after* step 4 had read the raw
   text, so an NFD accent after a backslash made a command (`\e`) and NFC didn't (TASK-168's finding).
2. **Case-fold** (`str.casefold()`, not `lower()` — `ß` → `ss`).
3. **Mark fold**: NFD, drop combining marks (combining class ≠ 0) whose base's Unicode NAME begins with
   LATIN, GREEK, CYRILLIC, HEBREW, ARABIC or EXTENDED ARABIC, or is an ASCII digit; **keep** marks that spell a distinct letter (Cyrillic breve,
   Arabic hamza, Thai tones, kana voicing, Indic signs); drop a stray combining mark (class ≠ 0) with no base; then NFC.
   After NFKC, a class-0 Mn/Mc mark that step 5 doesn't make invisible is a word character (e.g. U+0CE2), even
   with no base: a word made only of marks makes no token, but a letter after it joins it (U+0CE2 alone →
   nothing, U+0CE2 + `x` → one word); marks NFKC decomposes into combining marks are stray.
4. **LaTeX** (a three-state mask — keep / separate / join — so offsets survive): `\cmd{X}` → `X`; a bare
   `\cmd` outside math is dropped; math is `$…$` (Pandoc rule: opener followed by a non-space, closer
   preceded by a non-space and not followed by a digit, read on the NFKC form: a spacing accent `´` is a
   space and a mark, `½` begins with a digit), `$$…$$`, `\(…\)`, `\[…\]`, and inside it a
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

## Two served versions (guarantee 4)
`SERVED_TOKENIZERS` maps the current `TOKENIZER_VERSION` ("3") and the one before it ("2") to a `TokenizerForm`
(`nfkc_first`); code branches on the form, never on a version string. Every entry point takes the version:
`tokenize(text, version)`, `tokenize_with_tail`, `normalize`, `math_regions`, `first_math_end`, and above them
`lex(q, tokenizer)`, `parse(q, mode, tokenizer)` (`ParseResult.tokenizer_version`), `canonical_hash(canonical,
tokenizer)`, `Highlighter(ast, expansions, tokenizer)`, `ReferenceEngine(records, tokenizer=…)`. The version is
always the index's: `TantivyEngine.tokenizer_version`, read from its manifest. So a query against, and the
replay of a record pinned to, an index built with "2" is read exactly as it was, and its canonical_hash is the
one saved. An unknown version raises `ValueError` (a caller's bug). Version 2 is held byte-stable by a frozen
copy of the code it ran, `tests/unit/tokenizer_v2/` (`test_tokenizer_versions.py`), and every golden row runs
under both versions (`CHANGED_IN_3` holds version 3's tokens for the rows it changed). Retiring "2": the
index-versioning skill.

## Single source of truth
`backend/src/openproceedings/query/normalize.py` is the only implementation: `tokenize(text, version) ->
list[Token]` (each with the raw half-open code-point span it came from, for highlights: a math command's span
is its name; markup that opens a word (an accent macro such as `\"{O}del` or `\v{S}`, `\-`, or a math
`^`/`_`: `$^2x$` spans `^2x`) starts the span at its first character,
task-074; two spans overlap only on exactly one code point that folds to several pieces, `½` → `1`, `2`:
inside a U+0338 cluster each piece spans the raw characters it came from, except that pieces before the first
raw U+0345 end at it even if a later mark belongs to them, task-075; a Token is text, span and `op` only,
since task-075's `reach` was retired after decision-008; no span decides what parses: the lexer's detached-wildcard check reads
the folded pieces after the last word, `tokenize_with_tail(text) -> (tokens, Tail)`, decision-008) and
`normalize(text, version) -> list[str]`. Tokenizer 3 runs the loop below on the NFKC form of the text (`_view`;
a text already in NFKC, every ASCII one included, is its own form, so it costs one `is_normalized` check) and maps
each token's span back to the raw characters its characters came from (`_View.tokens`: a composed character
spans the raw ones it came from, an expanded one's pieces each span it; when interleaved marks would make spans
overlap, the first ends where the second starts, as tokenizer 2's task-075 rule does). It works character by character (with two exact shortcuts, task-073: a whole
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
| `Caf\é`, its NFD form `Caf\e` + U+0301, and the NFKC/NFKD forms | `caf`, `e` (tokenizer 3; NFD gave `caf` in 2) |
| `Erd\H{ő}s` in any form | `erdos` (tokenizer 3; NFD gave `erd`, `o`, `s` in 2) |
| `＼emph{x} and ＄\alpha＄` | `x`, `and`, `α` (tokenizer 3: the NFKC form's LaTeX) |
Add a row for every bug ever found; never delete one. A row a version changed keeps its old tokens and names
the new ones in that version's table (`CHANGED_IN_3`); the backslash + accent rows in every Unicode form are
`FORMS`, and a Hypothesis property (and the nightly exhaustive check, every code point in 16 contexts) holds that
all four forms of any text tokenize alike.

## TOKENIZER_VERSION bump rule
Bump when **any** input could tokenize differently than before — even if no golden case changes. A bump keeps
the version before it served: add the new form to `SERVED_TOKENIZERS`, drop the oldest (only once no record pins
an index built with it), freeze a copy of the old code beside the old one in `tests/unit/`, and run every golden
row under both. The
version is folded into `index_version` and `canonical_hash`, so old search records correctly report
`drifted` instead of falsely claiming `reproduced`. Refactors proven token-identical by the full-corpus
parity test do not bump.

## Checklist for a change here
- [ ] golden table extended with the case that motivated the change
- [ ] `TOKENIZER_VERSION` bumped (or parity run proves no change), the old version still served and frozen
- [ ] tokenizer-parity + differential suites green
- [ ] `exactness-guardian` review (routed automatically by `/review-gate`)
