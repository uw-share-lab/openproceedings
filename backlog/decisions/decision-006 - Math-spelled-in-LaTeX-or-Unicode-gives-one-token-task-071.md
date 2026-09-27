---
id: decision-006
title: Math spelled in LaTeX or Unicode gives one token (task-071)
date: '2026-09-26 17:03'
status: accepted
---
## Context

Abstracts write the same math two ways. OpenReview keeps authors' LaTeX (`$\alpha$`, `$\times$`,
`$O(n^2)$`); the proceedings pages and PMLR often render it as Unicode (`α`, `×`, `O(n²)`). Under tokenizer
1 the two spellings gave different tokens (`$\alpha$` → `alpha` but `α` → `α`; `$\leq$` → `leq` but `≤` →
nothing; `$n^2$` → `n 2` but `n²` → `n2`), so a query matched one source's text and missed the other's.
That would make decision-005's source precedence change what a search finds. Found 2026-09-26 while
comparing OpenReview and PMLR abstracts (task-071).

## Decision

The review lead chose (2026-09-26, asked with worked examples):

1. **Greek letters: the Unicode letter is the token.** Inside math, `\alpha` … `\omega`, the capitals and
   the `\var…` forms become the letter, which then folds like any other (`\Delta` → `δ`; `\epsilon`,
   `\varepsilon`, `ϵ` and `ε` → `ε`). A Greek command joins its neighbours as the letter would
   (`$\alpha\beta$` → `αβ`, `$\alpha_1$` → `α1`). A query must contain the letter: typing `alpha` finds
   only the spelled-out word.
2. **Operators and relations: the case-folded LaTeX command name is the token**, and each Unicode
   operator becomes that token as a word of its own (`5×3` → `5`, `times`, `3`). A LaTeX alias maps to
   its operator's one name (`\le` → `leq`, `\to` and `\implies` → `rightarrow`). Because tokens are
   case-folded, `→` and `⇒` share `rightarrow`, as `$\to$` and `$\Rightarrow$` already did.
3. **Super- and subscripts join**, as NFKC reads them (`n²` → `n2`): inside math, `^` or `_` followed by
   one ASCII letter or digit, or a braced run of them, joins it (`$n^2$` → `n2`, `$x_{ij}$` → `xij`).
   Anything else is unchanged (`$10^{-3}$` and `10⁻³` both → `10 3`). `$x^\alpha$` stays `x α`: NFKC
   reads `ᵅ` as the Latin `ɑ`, so no Unicode spelling could agree.

4. **Review additions (2026-09-26, the review lead chose "add them all"):** `∆` (U+2206) is read as `Δ`;
   `\ell` is `ℓ`, which NFKC reads as `l` (`$\ell_2$` and `ℓ₂` → `l2`); `∣`, `∗`, `⋆`, `⋯` and the long
   arrows `⟶ ⟹ ⟵ ⟸ ⟷ ⟺` join the table, with `\longrightarrow` and kin as aliases; `\not\in` and `\not=`
   are `notin` and `neq`, like `∉` and `≠`.
5. **How the rules apply:** the operator table is consulted **after NFKC** (so `∬` → `int int`, `𝛁` →
   `nabla`, `ŀ` and `l·` agree), and a character whose combining marks include a U+0338 slash is read
   with its marks as one NFKC cluster, so a decomposed `∉` is `notin` (never `in`) and full-width `＝` +
   slash is `≠`, whatever the marks' order. A Greek letter right after another command's name starts a
   new word (`$\hat\theta$` → `hat θ`), as the Unicode `θ̂` gives `θ`; after a letter it joins
   (`$x\alpha$` → `xα`). Only ASCII letters and digits join after `^`/`_`.
6. **Negated relations** (verification round): `≰ ≱ ⊄ ⊈ ⊅ ⊉ ∌ ∄ ∤ ∦ ≢ ≁ ≉ ≇` are tokens of their own
   (`nleq`, `nsubset`, …), matching the `\n…` commands, `\not` followed by the operator (spaces allowed,
   as in TeX) and an operator command followed by a U+0338 slash.
7. **Queries** (the review lead chose "warn, keep as terms"): a logic sign (`∨`, `∧`, `¬`, anywhere in a word, after NFKC) is
   searched as its word with `WARN_LOOKALIKE_OPERATOR` saying it is not OR/AND/NOT; a spelled Greek name
   (`alpha`) gets `WARN_SPELLED_GREEK` pointing to the letter; a wildcard straight after an operator is
   `PARSE_WILDCARD_DETACHED`.

Commands outside math are still markup (dropped), as LaTeX treats them. `TOKENIZER_VERSION` is 2; it was
first committed with rules 1–3 and completed with 4–5 on the same unmerged branch before any index or
search record used it, so it stays 2.

### The operator table (`backend/src/openproceedings/query/mathsyms.py`)

Tokens marked **yes** are also ordinary words (`mathsyms.ALSO_WORDS`), so a search for the word also
finds the symbol (a search for `in` or `times` matches `x ∈ S` and `5×3`). The review lead accepted this
for `times` and `in` and was told the full list. `·` is also used as a separator in titles
(`Foo · Bar` → `foo cdot bar`). The table is generated (`mathsyms.operator_table()`); a test fails if this
copy and the code differ.

| Token | Unicode | LaTeX (inside math) | Also an ordinary word |
|---|---|---|---|
| `approx` | ≈ | `\approx` | **yes** |
| `ast` | ∗ | `\ast` |  |
| `cap` | ∩ | `\cap` | **yes** |
| `cdot` | · ⋅ | `\cdot` |  |
| `cdots` | ⋯ | `\cdots` |  |
| `circ` | ∘ | `\circ` |  |
| `cong` | ≅ | `\cong` |  |
| `cup` | ∪ | `\cup` | **yes** |
| `div` | ÷ | `\div` | **yes** |
| `emptyset` | ∅ | `\emptyset`, `\varnothing` |  |
| `equiv` | ≡ | `\equiv` |  |
| `exists` | ∃ | `\exists` | **yes** |
| `forall` | ∀ | `\forall` |  |
| `geq` | ≥ ⩾ | `\ge`, `\geq`, `\geqslant` |  |
| `gg` | ≫ | `\gg` |  |
| `in` | ∈ | `\in` | **yes** |
| `infty` | ∞ | `\infty` |  |
| `int` | ∫ | `\int` | **yes** |
| `leftarrow` | ← ⇐ ⟵ ⟸ | `\Leftarrow`, `\Longleftarrow`, `\gets`, `\leftarrow`, `\longleftarrow` |  |
| `leftrightarrow` | ↔ ⇔ ⟷ ⟺ | `\Leftrightarrow`, `\Longleftrightarrow`, `\iff`, `\leftrightarrow`, `\longleftrightarrow` |  |
| `leq` | ≤ ⩽ | `\le`, `\leq`, `\leqslant` |  |
| `ll` | ≪ | `\ll` | **yes** |
| `mapsto` | ↦ | `\mapsto` |  |
| `mid` | ∣ | `\mid` | **yes** |
| `mp` | ∓ | `\mp` | **yes** |
| `nabla` | ∇ | `\nabla` |  |
| `napprox` | ≉ | `\napprox`, `\not\approx` |  |
| `ncong` | ≇ | `\ncong`, `\not\cong` |  |
| `neg` | ¬ | `\lnot`, `\neg` | **yes** |
| `neq` | ≠ | `\ne`, `\neq`, `\not=` |  |
| `nequiv` | ≢ | `\nequiv`, `\not\equiv` |  |
| `nexists` | ∄ | `\nexists`, `\not\exists` |  |
| `ngeq` | ≱ | `\ngeq`, `\not\ge`, `\not\geq`, `\not\geqslant` |  |
| `ni` | ∋ | `\ni` | **yes** |
| `nleq` | ≰ | `\nleq`, `\not\le`, `\not\leq`, `\not\leqslant` |  |
| `nmid` | ∤ | `\nmid`, `\not\mid` |  |
| `notin` | ∉ | `\not\in`, `\notin` |  |
| `notni` | ∌ | `\not\ni`, `\notni` |  |
| `nparallel` | ∦ | `\not\parallel`, `\nparallel` |  |
| `nsim` | ≁ | `\not\sim`, `\nsim` |  |
| `nsubset` | ⊄ | `\not\subset`, `\nsubset` |  |
| `nsubseteq` | ⊈ | `\not\subseteq`, `\nsubseteq` |  |
| `nsupset` | ⊅ | `\not\supset`, `\nsupset` |  |
| `nsupseteq` | ⊉ | `\not\supseteq`, `\nsupseteq` |  |
| `odot` | ⊙ | `\odot` |  |
| `oplus` | ⊕ | `\oplus` |  |
| `otimes` | ⊗ | `\otimes` |  |
| `parallel` | ∥ | `\parallel` | **yes** |
| `partial` | ∂ | `\partial` | **yes** |
| `perp` | ⊥ | `\perp` |  |
| `pm` | ± | `\pm` | **yes** |
| `prod` | ∏ | `\prod` | **yes** |
| `propto` | ∝ | `\propto` |  |
| `rightarrow` | → ⇒ ⟶ ⟹ | `\Longrightarrow`, `\Rightarrow`, `\implies`, `\longrightarrow`, `\rightarrow`, `\to` |  |
| `setminus` | ∖ | `\setminus` |  |
| `sim` | ∼ | `\sim` | **yes** |
| `simeq` | ≃ | `\simeq` |  |
| `sqrt` | √ | `\sqrt` |  |
| `star` | ⋆ | `\star` | **yes** |
| `subset` | ⊂ | `\subset` | **yes** |
| `subseteq` | ⊆ | `\subseteq` |  |
| `sum` | ∑ | `\sum` | **yes** |
| `supset` | ⊃ | `\supset` |  |
| `supseteq` | ⊇ | `\supseteq` |  |
| `times` | × | `\times` | **yes** |
| `vee` | ∨ | `\lor`, `\vee` |  |
| `wedge` | ∧ | `\land`, `\wedge` | **yes** |

## Consequences

- Every `canonical_hash` changes (it covers `TOKENIZER_VERSION`, decision-003): the Trust-Evals snapshot
  hashes were regenerated; the canonical strings and identification queries are unchanged.
- The index must be built with tokenizer 2 (task-023 starts after this).
- A methods section should say that math is matched by its Unicode spelling and operator names.
- Changing a table row changes what text tokenizes to, so it is a new `TOKENIZER_VERSION`.
