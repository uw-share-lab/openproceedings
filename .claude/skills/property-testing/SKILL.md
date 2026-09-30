---
name: property-testing
description: How openproceedings uses Hypothesis — strategies for tokens, query strings and ASTs, the properties that must hold (canonical idempotence, AST round-trip, parser totality, TantivyEngine == ReferenceEngine, dedup invariants), settings profiles (PR CI 200 examples in parallel, nightly 2,000 and 50,000), deadlines, shrinking, and turning every counterexample into a permanent golden case. Use when writing or reviewing a property test or strategy, triaging a Hypothesis failure, or tuning the differential suite.
---

# Property testing (Hypothesis)

## Profiles — selected by `HYPOTHESIS_PROFILE`
Register in `backend/tests/conftest.py`:
| Profile | `max_examples` | Deadline | Used by |
|---|---|---|---|
| `dev` | 200 | 500 ms | local loop (default), `make test` under pytest-xdist |
| `pr` | 200 | 2 s | `test` workflow on every PR, under pytest-xdist: the dev count with the ci deadline, so a slow example on a shared runner doesn't fail the required check (TASK-127) |
| `ci` | **2,000** | 2 s | `nightly` workflow's `suite-ci` job: the whole backend suite, under pytest-xdist (differential@2k) |
| `nightly` | **50,000** | `None` | `nightly` workflow's property jobs (differential@50k: task-057) |
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
vocabularies), `negative_asts()`, `engine_asts()` (any tree an engine may get, including bare and all-negative ones; task-028;
each tree strategy takes a `Vocab`, default the 200-record fixture's, `synthetic_5k.vocab()` for the 5k corpus),
`leaves()`, `filters()` (every track and status of the vocabulary) and `queries()` (strings). Tokens come from the
200-record fixture's real term dictionary plus awkward extras (operator words, filter values as text,
digits, Thai, kana, CJK). Import it as `from tests.strategies import …`. Properties over them live in
`tests/unit/test_properties.py` (round-trip without printing-caused warnings, match-set preservation by
the oracle, all-negative rejection, Scholar mode reads canonical strings identically). PR CI runs the `pr`
profile (200) in parallel; the nightly workflow runs the whole suite at `ci` (2,000) and every property at
`nightly` (50,000), the latter split into an
oracle-backed job and the rest (about 35 and 20 minutes locally). Counterexamples found so
far are golden rows (`("0", "0")` in test_canonical.py; `trust (trust OR track:main)` in test_defaults.py).
Not yet: stems near the 200-expansion cap (needs the 5k fixture, task-057).
`year_edit_cases()` (TASK-145) builds queries whose year clause is toggleable, in either mode, instead of
drawing `clause_queries()`/`near_cap_queries()` and `assume()`ing it: the toggleability rules are in its grammar,
and only the padding toward the length and depth caps is cut back, by parsing the query and its widest year
edit. Some cases are near misses (one step past a rule; a few percent to a quarter, varying by run) that `filter_clauses` must refuse with that
reason, so the property still sees a clause wrongly reported toggleable.

## Properties that must hold
1. **Parser totality:** `parse(s)` never raises for any `str`; bad input yields `errors`.
2. **Canonical idempotence:** `parse(parse(s).canonical).canonical == parse(s).canonical`.
3. **Round-trip:** `parse(render(ast)).ast == ast` for generated ASTs.
4. **Differential:** `TantivyEngine.match_ids(ast) == ReferenceEngine.match_ids(ast)` on the 5k fixture.
5. **Ranking invariance:** `set(ids)` identical across `sort` values, and with the semantic layer on/off once 06 is built.
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
- `--hypothesis-show-statistics` counts as invalid both rejections (`assume()`, `.filter()`; listed as "gave up
  because") and Hypothesis's own overruns ("exceeded maximum test case size" in `HYPOTHESIS_EXPERIMENTAL_OBSERVABILITY`
  output, no "gave up" line). Recursive strategies overrun all through a run (`clause_queries()` alone: about a
  third of cases; `year_edit_cases()`: 9 to 20%, none rejected), so read the "gave up" lines for filtering, not
  the invalid count (TASK-145).
- A property that can't fail is not a test: mutation-check it once by breaking the code it covers.
