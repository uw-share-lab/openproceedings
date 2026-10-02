---
name: property-testing
description: How openproceedings uses Hypothesis — strategies for tokens, query strings and ASTs, the properties that must hold (canonical idempotence, AST round-trip, parser totality, TantivyEngine == ReferenceEngine, dedup invariants), settings profiles (PR CI 200 examples in parallel, nightly 2,000 and 50,000), deadlines, shrinking, and turning every counterexample into a permanent golden case. Use when writing or reviewing a property test or strategy, triaging a Hypothesis failure, or tuning the differential suite.
---

# Property testing (Hypothesis)

## Profiles — selected by `HYPOTHESIS_PROFILE`
Register in `backend/tests/conftest.py`:
| Profile | `max_examples` | Deadline | Used by |
|---|---|---|---|
| `dev` | 200 | `None`, and `too_slow` suppressed | local loop (default), `make test` under pytest-xdist: no wall-clock checks (decision-024, below) |
| `pr` | 200 | 2 s | `test` workflow on every PR, under pytest-xdist: the dev count with the ci deadline, so a slow example on a shared runner doesn't fail the required check (TASK-127); `derandomize=True` (decision-024) |
| `ci` | **2,000** | 2 s | `nightly` workflow's `suite-ci` job: the whole backend suite but the differential, under pytest-xdist |
| `nightly` | **50,000** | `None` | `nightly` workflow's property jobs, under pytest-xdist, and its `differential` job: 50,000 in total, 8 independent parallel runs of 6,250 (`OP_DIFFERENTIAL_SHARDS=8`, each with its own `--hypothesis-seed`; TASK-057) |
Every profile sets `print_blob=True` (so a CI failure prints a `@reproduce_failure` blob). The
Hypothesis example database (`.hypothesis/`) is gitignored; CI failures are reproduced from the blob.

**Every profile's parent is Hypothesis's `default` profile** (`BASE` in conftest), never the loaded one. Where the
`CI` environment variable is set, as on GitHub Actions, Hypothesis loads its own built-in `ci` profile at import:
`derandomize=True`, `database=None`, `deadline=None` and `too_slow` suppressed. A profile registered without a
parent copies whatever is loaded, so until TASK-146 the `pr`, `ci` and `nightly` runs in CI were derandomized
(the same examples on every run) and suppressed `too_slow`, unlike the same profiles locally. The case table
`test-hypothesis-profiles.sh` runs the profile tests with `CI` unset and with `CI=true`; a local run doesn't
show the difference otherwise. Only `pr` is derandomized, on purpose (decision-024): the required gate must be
deterministic, running the same examples on every PR, so a PR never fails for a counterexample in code it didn't
touch. It still keeps every health check, `too_slow` included. Exploration belongs to `ci` and `nightly`; a
nightly failure is triaged into a Backlog task carrying its `@reproduce_failure` blob.

## Health checks and deadlines (decision-024, TASK-146)
- **Wall-clock checks are gates only on CI runners.** A deadline and the `too_slow` health check time the
  machine as well as the code. Locally, `make test` shares 8 CPUs with other worktrees' runs (load 90 to 340
  measured on 2026-09-30), so `dev` has no deadline and suppresses `too_slow`. `pr` (every PR), `ci` and
  `nightly` keep their deadline (`nightly` has none) and suppress no health check, so a slow strategy or
  example still fails the PR's required `test` job. `backend/tests/unit/test_hypothesis_profiles.py` shows a
  sleeping strategy failing `pr` and passing `dev`; its mutants are in `.claude/scripts/mutants/gates.json`
  (`profiles:`).
- **Every other health check is on in every profile.** `data_too_large`, `filter_too_much` and
  `large_base_example` depend only on the strategy and the seed, not on load. Fix the strategy instead of
  suppressing them (TASK-145 for `filter_too_much`).
- **No test suppresses a health check itself.** `test_no_test_suppresses_a_health_check_itself` fails on any
  `suppress_health_check`, `HealthCheck`, `get_profile(` or `load_profile(` outside `conftest.py`, so no test
  borrows `dev`'s suppression either. A strategy that seems to need one gets its health-check window measured
  first (below); if it really does, that is a change to this rule and to decision-024. Per test,
  `deadline=None` is allowed, with a comment saying why, for an example that is long by design (the oracle
  over 5k records, several crawls, near-cap queries). It keeps `too_slow`, with a 30 s limit. Every one in
  `backend/tests` has its comment; five properties whose examples took at most ~55 ms (`test_tantivy_200.py`'s
  combinations, the facet-click property in `test_clauses.py`, three message properties in
  `test_properties.py`) went back to the profile deadline (TASK-146).
- **How the checks measure.** Hypothesis times the draws of the first 10 valid examples. It fails `too_slow`
  above the larger of 1 s and 5 deadlines: 10 s at `pr` and `ci`, 30 s with no deadline (`nightly`), 2.5 s
  under the old 500 ms `dev` deadline. It fails `data_too_large` at 20 overruns before 10 valid examples.
  Measured on 2026-10-01 at `pr`: every property's window was at most 0.75 s. Over 300 seeds,
  `engine_asts(vocab())` and the facets test's `filtered_asts()` took at most 0.84 s and overran at most once.
  So the per-test `too_slow` and `data_too_large` suppressions in the differential, facets and highlight-speed
  tests were removed. So was search-overlap's `function_scoped_fixture` suppression, which did nothing because
  its fixture is module-scoped.
- **The case behind the rule.** `test_a_split_always_has_the_id_count` failed `too_slow` at load ~90. In a fresh
  worktree, `.hypothesis/unicode_data` is empty, and the first `st.text()` draw builds it, which takes ~0.85 s
  of draw time. Three times slower, that exceeded the old 2.5 s `dev` limit. On a CI runner it is ~9% of the
  10 s limit.
- **Check timing locally** on a quiet machine with `HYPOTHESIS_PROFILE=pr uv run pytest <file>`, which is
  what the PR gate runs.
- **Load recipe** (to show a check depends on load): start `yes > /dev/null &` four times per CPU, wait ~45 s
  for the load average to climb, run the test with `rm -rf .hypothesis` before each run, record `uptime`, then
  kill those PIDs only. On 2026-10-01, at load 76 to 123, the old `dev` profile failed the authors property
  `too_slow` 5 times out of 5 and the new `dev` passed 5 times out of 5.

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
`nightly` (50,000), the latter as a 5-part matrix under pytest-xdist split by measured time per test (the near-cap
replay property alone, the other oracle-backed ones, `unit/engine`, `unit/ingest`, the rest), the year-edit
property's 4-way split (`OP_YEAR_EDIT_SHARDS`, a `year-edits` job), and the differential's own 8-way split. Those steps set `OP_EARLY_FAILURES=1` (`conftest.py`): a failure's falsifying
example and blob are printed when it fails, so a step later interrupted at its time limit still shows them
(`backend/tests/unit/test_early_failures.py`, case table `.claude/scripts/tests/test-early-failures.sh`, mutants in
`gates.json`). Counterexamples found so
far are golden rows (`("0", "0")` in test_canonical.py; `trust (trust OR track:main)` in test_defaults.py).
Stems at the 200-expansion cap: the 5k corpus's stems jump from 117 terms to 278, so `synthetic_5k.cap_records()`
adds 20 records whose words make `qca*` expand to 199 terms, `qcb*` to 200 and `qcc*` to 201 (refused), and
`cap_vocab()` (`Vocab.cap`) draws them one stem in ten; the differential suite's engines search both (TASK-057).
`year_edit_cases()` (TASK-145) builds queries whose year clause is toggleable, in either mode, instead of
drawing `clause_queries()`/`near_cap_queries()` and `assume()`ing it: the toggleability rules are in its grammar,
including year filters nested beside the clause and an OR of year filters as the clause (spec 02: neither blocks
the edit), and only the padding toward the length and depth caps is cut back, by parsing the query and its widest
year edit. Some cases are near misses (one step past a rule; a few percent to a quarter, varying by run) that
`filter_clauses` must refuse with that reason, so the property still sees a clause wrongly reported toggleable.
`click_cases()` and `wrap_cases()` (TASK-153) do the same for the single-value-click and one-wrap properties in
`test_clauses.py`, which had `assume()`d a parse: `click_cases` builds every field's clauses in every shape with the
parser's rules in its grammar (a positive anchor, every OR branch positive, parts written together only where a
`)` meets a `(`), `wrap_cases` is a `queries()` string or near-cap parts, and both cut padding back by parsing. They
yield a `ParseCase`; roughly one case in ten is a near miss (every conjunct negated, a word written before a group,
one step past the length or depth cap) that `parse` must refuse with its code. Rejections went from 27 to 32% of
draws (`assume()`) to none, and invalid draws to 5 to 16% over random `pr` runs (all overruns; derandomized `pr`:
one-wrap 8/68, click 18/218).

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
- **The counterexample may be the oracle's fault.** Before triaging, print the shrunk input and the values the
  assertion compared; the failure text can mislead (a strategy constant made an ICLR input read as NeurIPS). If the
  code matches another documented invariant the oracle contradicts, decide which one wins before touching the code.
  Code that recomputes derived rows from the final state breaks "nothing is removed". Write the oracle as "only X may
  change, and nothing it named is lost" (TASK-154).

## Gotchas
- Build the fixture index once per session (`scope="session"` fixture), not per example — otherwise the
  deadline measures index build.
- `@settings(deadline=...)` flakes on shared CI runners; prefer the profile deadline and raise it rather
  than disabling it in `ci`. A per-test `deadline=None` follows §Health checks and deadlines (a comment saying
  why the example is long by design). A deadline or `too_slow` failure seen only locally under load is not a finding
  (`dev` no longer has either); one in CI is.
- Don't `assume()` away large parts of the space (e.g. `assume(no wildcards)`); Hypothesis will report
  `FailedHealthCheck` or silently test less. Constrain the strategy instead.
- `--hypothesis-show-statistics` counts as invalid both rejections (`assume()`, `.filter()`; listed as "gave up
  because") and Hypothesis's own overruns ("exceeded maximum test case size" in `HYPOTHESIS_EXPERIMENTAL_OBSERVABILITY`
  output, no "gave up" line). Recursive strategies overrun all through a run (the since-removed `clause_queries()`
  alone: about a third of cases; `year_edit_cases()`: 10 to 20%, none rejected), so read the "gave up" lines for
  filtering, not the invalid count (TASK-145).
- Nearly all of those overruns are Hypothesis's mutator, not generation: after each valid case it copies a span over
  another span with the same label, gives the result exactly as many choices as it had, and a copy that makes the
  case draw more (a leaf becomes a group, a list gets longer) overruns. Every `st.integers`/`st.booleans` draw
  shares one label, and every `st.lists` element another, so a decision that changes how much is drawn after it gets
  its own `st.sampled_from` (in `strategies.py`: `_GROUP_SIZES`, `_QUERY_NODES`, the values of a clause drawn as a
  count and a permutation, not a list). That took `click_cases`' overruns from 18 to 27% of cases to 5 to 12% over
  random `pr` runs of the property (TASK-153).
- A property that can't fail is not a test: mutation-check it once by breaking the code it covers.
