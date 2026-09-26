---
name: property-testing
description: How openproceedings uses Hypothesis — strategies for tokens, query strings and ASTs, the properties that must hold (canonical idempotence, AST round-trip, parser totality, TantivyEngine == ReferenceEngine, dedup invariants), settings profiles (CI 2,000 examples vs nightly 50,000), deadlines, shrinking, and turning every counterexample into a permanent golden case. Use when writing or reviewing a property test or strategy, triaging a Hypothesis failure, or tuning the differential suite.
---

# Property testing (Hypothesis)

## Profiles — selected by `HYPOTHESIS_PROFILE`
Register in `backend/tests/conftest.py`:
| Profile | `max_examples` | Deadline | Used by |
|---|---|---|---|
| `dev` | 200 | 500 ms | local loop (default) |
| `ci` | **2,000** | 2 s | `test` workflow (differential@2k) |
| `nightly` | **50,000** | `None` | `nightly` workflow (differential@50k) |
Also set `print_blob=True` (so a CI failure prints a `@reproduce_failure` blob) and
`suppress_health_check=[HealthCheck.too_slow]` only for the differential suite, with a comment. The
Hypothesis example database (`.hypothesis/`) is gitignored; CI failures are reproduced from the blob.

## Strategies (`backend/tests/strategies.py`, one shared module)
- **Tokens:** draw mostly from the fixture's **actual term dictionary** (so queries hit documents), mixed
  with rare terms, near-misses of real terms (`benchmark` vs `benchmarks`), and tokens that exercise
  normalization (ligatures, diacritics, full-width, digits). Pure random text almost never matches and
  tests nothing.
- **Wildcards:** a real term's prefix of length ≥3 plus `*` or `$`; include stems near the 200-expansion
  cap to hit the error path.
- **ASTs:** `st.recursive` over `Term | Phrase | Wildcard | Near | Filter`, combined by `And | Or | Not`,
  with bounded depth (≈4) and width. Filters draw from the real vocabularies (`venue`, `year` ranges,
  `track`, `status`). Never generate an all-negative query as a *valid* AST — generate it separately and
  assert it errors.
- **Query strings:** render ASTs (native and Scholar mode), plus arbitrary `st.text()` for totality.
- **Records (dedup):** pairs that differ only in venue, only in year, or with a missing year.

**As built (task-017):** `backend/tests/strategies.py` has `asts()` (valid trees with a positive
anchor; every node type, wildcard phrase items, NEAR with same-field leaves, filters from the real
vocabularies), `negative_asts()`, `leaves()`, `filters()` and `queries()` (strings). Tokens come from the
200-record fixture's real term dictionary plus awkward extras (operator words, filter values as text,
digits, Thai, kana, CJK). Import it as `from tests.strategies import …`. Properties over them live in
`tests/unit/test_properties.py` (round-trip without printing-caused warnings, match-set preservation by
the oracle, all-negative rejection, Scholar mode reads canonical strings identically). CI runs the `ci`
profile (2,000); the nightly workflow runs every property at `nightly` (50,000), split into an
oracle-backed job and the rest (about 35 and 20 minutes locally). Counterexamples found so
far are golden rows (`("0", "0")` in test_canonical.py; `trust (trust OR track:main)` in test_defaults.py).
Not yet: stems near the 200-expansion cap (needs the 5k fixture, task-057).

## Properties that must hold
1. **Parser totality:** `parse(s)` never raises for any `str`; bad input yields `errors`.
2. **Canonical idempotence:** `parse(parse(s).canonical).canonical == parse(s).canonical`.
3. **Round-trip:** `parse(render(ast)).ast == ast` for generated ASTs.
4. **Differential:** `TantivyEngine.match_ids(ast) == ReferenceEngine.match_ids(ast)` on the 5k fixture.
5. **Ranking invariance:** `set(ids)` identical across `sort` values and with the semantic layer on/off.
6. **Dedup:** never merges across venue or year, never merges on `(title, "")`, and is idempotent.
7. **Tokenizer:** `normalize(" ".join(normalize(x))) == normalize(x)`.

## Shrinking and counterexamples
- Let Hypothesis shrink; don't catch exceptions inside the test body, which blocks shrinking.
- Keep strategies shrink-friendly: build from simple parts (`st.one_of` with the simplest case first) so
  a failure reduces to a two-term query, not a 40-node tree.
- **Every counterexample becomes permanent.** (1) Add `@example(...)` with the shrunk input to the
  property. (2) Add a golden case in `backend/tests/golden/` with the minimal query and the expected ID set
  taken from `ReferenceEngine` (checked by hand). (3) Then fix. `differential-tester` minimizes; the golden
  case outlives any strategy change.

## Gotchas
- Build the fixture index once per session (`scope="session"` fixture), not per example — otherwise the
  deadline measures index build.
- `@settings(deadline=...)` flakes on shared CI runners; prefer the profile deadline and raise it rather
  than disabling it in `ci`.
- Don't `assume()` away large parts of the space (e.g. `assume(no wildcards)`); Hypothesis will report
  `FailedHealthCheck` or silently test less. Constrain the strategy instead.
- A property that can't fail is not a test: mutation-check it once by breaking the code it covers.
