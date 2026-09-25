---
name: scholar-syntax-compat
description: How Scholar/Publish-or-Perish query strings are accepted in `mode="scholar"` — `|` as OR, `source:` mapped through an alias table to `venue:` (PMLR → ICML with a warning), PoP `$` read as the WoS wildcard, and every rewrite reported in `translations[]` — plus the Trust-Evals strings and source values used as fixtures. Use when writing or reviewing query/compat.py, the source alias table, translation notices, or when a review's existing search string fails to parse.
---

# Scholar / PoP syntax compatibility (spec 02 §Compatibility input modes)

The review's existing strings must work **unchanged**, or come back with a precise explanation. Compat mode
is a front end to the native grammar. It never changes what a native query means.

## Contract
- `parse(q, mode="scholar")` accepts `OR` / `|`, `source:`, quoted phrases and `-` negation.
- Output is a **native** AST and a native canonical string. `mode` is recorded with the input (search
  records, `/search?mode=`), but the canonical string contains no compat syntax. Property:
  `parse(parse(q, "scholar").canonical, "native").canonical == parse(q, "scholar").canonical`.
- Every rewrite becomes a `translations[]` Diagnostic `{code, message, span}` pointing at the input text.
  A rewrite without a notice breaks guarantee 6.
- Code: `backend/src/openproceedings/query/compat.py`. Grammar rules: `.claude/skills/query-grammar/SKILL.md`.

## `source:` alias table
Match on the value after the token contract is applied (case-folded, punctuation split, whitespace
collapsed). Match exactly. **Never** as a substring (Scholar's `source:` is a fuzzy substring match; ours is
not).

| `source:` value (as the review's exports used it) | → | Notice |
|---|---|---|
| `NeurIPS`, `"neural information processing systems"`, `"advances in neural information processing systems"` | `venue:NeurIPS` | translation |
| `ICLR`, `"international conference on learning representations"` | `venue:ICLR` | translation |
| `ICML`, `"international conference on machine learning"` | `venue:ICML` | translation |
| `PMLR`, `"proceedings of machine learning research"` | `venue:ICML` | **warning**: PMLR also hosts other venues; only ICML is indexed |

Unknown value → **error** listing the known aliases. Several `source:` clauses OR'd together (the review ran
one export per source) collapse to one `venue:(… OR …)` clause, with one notice per clause.

## Other rewrites
| Input | Native | Notice |
|---|---|---|
| `a \| b` | `a OR b` | none needed (`|` is in the native EBNF) |
| `model$` | WoS zero-or-one wildcard | "PoP `$` interpreted as zero-or-one character" |
| lowercase `or` | term `or` + warning | same as native |
| an operator we don't support (e.g. Scholar's `intitle:`, `allintitle:`) | error, never ignored | verify the exact list at implementation time; add a fix hint pointing to `title:` |

## What compat mode does not do
- It adds no stemming. Scholar matched `benchmarks` for `benchmark`. We don't, and the 07 Scholar comparison
  counts that difference. Never add stemming to "match Scholar".
- It does not search full text. That difference is also counted in 07.
- It does not drop the default filters. They are added and made explicit exactly as in native mode
  (`.claude/skills/default-filters/SKILL.md`).

## Fixtures
- The six Trust-Evals protocol variants (main, narrow, human-centred, LLM-as-judge, including **Most
  Updated**) must parse without errors, with their canonical forms snapshot-tested under
  `backend/tests/golden/`. Copy the strings verbatim from the protocol document. Never retype them from memory.
- Every source value above gets a translation fixture, including `"proceedings of machine learning
  research"`, which returned 0 hits in Scholar for 2020–2024 but must still translate (with the PMLR warning).
- A snapshot change to a fixture's canonical form needs a decision record. It changes `canonical_hash` for
  every saved record that used it.
