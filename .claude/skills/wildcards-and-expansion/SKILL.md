---
name: wildcards-and-expansion
description: Exact semantics of the two opt-in suffix wildcards (`*` zero-or-more, `$` zero-or-one in Web of Science style), the 3-character stem minimum, expansion against the index term dictionary, the returned expansion list, and the 200-term cap. Use when touching wildcard lexing, Engine.expand, Wildcard compilation or evaluation, expansion display, or any complaint that a plural "should have matched".
---

# Wildcards and expansion (spec 02 §Rules, spec 03 §AST → Tantivy)

Wildcards are the **only** way to get plural or suffix matching (guarantee 1). They are explicit, suffix-only,
and every expansion is shown (guarantee 6).

## Semantics (over normalized tokens)
Normalize the stem first with `normalize.py` (`LLM$` → stem `llm`). Then, for vocabulary token `t`:

| Form | Matches `t` when | Example |
|---|---|---|
| `stem*` | `t.startswith(stem)` (includes `t == stem`) | `benchmark*` → benchmark, benchmarks, benchmarking, benchmarked |
| `stem$` | `t == stem` or (`len(t) == len(stem)+1` and `t.startswith(stem)`) | `model$` → model, models (and `modelx` if it exists; `$` is any one letter or digit) |

- Stem before `*` must be **≥ 3 characters** after normalization; shorter → error with a hint. The spec
  states the minimum for `*`; whether `$` shares it is a decision to record (`LLM$` has a 3-char stem, so
  the Trust-Evals strings don't settle it).
- Suffix only. `*bench`, `be*ch` or `$` mid-word → error, never a silent literal.
- A stem that normalizes to several tokens (`vision-lang*`) or a wildcard inside a phrase is not settled by
  the spec. Error until a decision record says otherwise.

## Expansion
- Expand against the **term dictionary of the `index_version` being searched**: the union of `title` and
  `abstract` terms (the Tantivy FST, via term streaming or `RegexQuery`). `ReferenceEngine` expands against
  the vocabulary it builds from the snapshot's normalized tokens. The two lists must be identical, and the
  differential suite checks it.
- The result is an explicit OR of exact terms. Return the sorted list to the caller as `expansions`
  (API, CLI `--explain`, and UI).
- **More than 200** distinct expanded terms → **error**, suggesting a longer stem. Never truncate. Never
  take the top-N by frequency.
- Zero expansions is not an error. It matches nothing. Surface a warning so the user sees it.
- The canonical string keeps `benchmark*` unexpanded. The same canonical string on a new `index_version`
  can expand differently. That is what "drifted" means for a search record, and `index_version` pins it.

## Scholar/PoP mode
PoP's `$` gets the WoS reading above, with a notice in `translations[]`. See
`.claude/skills/scholar-syntax-compat/SKILL.md`.

## Budget
Up to 200 terms must expand in **< 50 ms** (spec 03 §Performance). Stream the FST by prefix. Never scan the
whole vocabulary per query in the Tantivy path. A full scan is fine in the oracle.

## Gotchas
- `LLM` does **not** match `LLMs`. The golden table depends on users writing `LLM$` or `LLM*`. Never "help"
  by adding plural forms.
- `trust*` matches trustworthy, trustworthiness **and** trustee, trusted. Don't cap it by meaning. Showing
  the list is the fix.
- Case: expand on normalized forms. The term dictionary only ever holds normalized tokens.

## Checklist
- [ ] golden cases for `*`, `$`, stem < 3, over-cap, zero-expansion
- [ ] expansion list returned and equal between engines
- [ ] benchmark for a 200-term expansion
