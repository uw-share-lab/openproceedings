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

Commands outside math are still markup (dropped), as LaTeX treats them. `TOKENIZER_VERSION` is 2.

### The operator table (`backend/src/openproceedings/query/mathsyms.py`)

Tokens marked **yes** are also ordinary words, so a search for the word also finds the symbol (a search
for `in` or `times` matches `x ∈ S` and `5×3`). The review lead accepted this for `times` and `in`;
the others were not asked about individually.

| Token | Unicode | LaTeX (inside math) | Also an ordinary word |
|---|---|---|---|
| `approx` | ≈ | `\approx` |  |
| `cap` | ∩ | `\cap` | **yes** |
| `cdot` | · ⋅ | `\cdot` |  |
| `circ` | ∘ | `\circ` |  |
| `cong` | ≅ | `\cong` |  |
| `cup` | ∪ | `\cup` | **yes** |
| `div` | ÷ | `\div` |  |
| `emptyset` | ∅ | `\emptyset`, `\varnothing` |  |
| `equiv` | ≡ | `\equiv` |  |
| `exists` | ∃ | `\exists` | **yes** |
| `forall` | ∀ | `\forall` |  |
| `geq` | ≥ ⩾ | `\ge`, `\geq`, `\geqslant` |  |
| `gg` | ≫ | `\gg` |  |
| `in` | ∈ | `\in` | **yes** |
| `infty` | ∞ | `\infty` |  |
| `int` | ∫ | `\int` |  |
| `leftarrow` | ← ⇐ | `\Leftarrow`, `\gets`, `\leftarrow` |  |
| `leftrightarrow` | ↔ ⇔ | `\Leftrightarrow`, `\iff`, `\leftrightarrow` |  |
| `leq` | ≤ ⩽ | `\le`, `\leq`, `\leqslant` |  |
| `ll` | ≪ | `\ll` |  |
| `mapsto` | ↦ | `\mapsto` |  |
| `mp` | ∓ | `\mp` |  |
| `nabla` | ∇ | `\nabla` |  |
| `neg` | ¬ | `\lnot`, `\neg` |  |
| `neq` | ≠ | `\ne`, `\neq` |  |
| `ni` | ∋ | `\ni` |  |
| `notin` | ∉ | `\notin` |  |
| `odot` | ⊙ | `\odot` |  |
| `oplus` | ⊕ | `\oplus` |  |
| `otimes` | ⊗ | `\otimes` |  |
| `parallel` | ∥ | `\parallel` | **yes** |
| `partial` | ∂ | `\partial` | **yes** |
| `perp` | ⊥ | `\perp` |  |
| `pm` | ± | `\pm` | **yes** |
| `prod` | ∏ | `\prod` |  |
| `propto` | ∝ | `\propto` |  |
| `rightarrow` | → ⇒ | `\Rightarrow`, `\implies`, `\rightarrow`, `\to` |  |
| `setminus` | ∖ | `\setminus` |  |
| `sim` | ∼ | `\sim` |  |
| `simeq` | ≃ | `\simeq` |  |
| `sqrt` | √ | `\sqrt` |  |
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
