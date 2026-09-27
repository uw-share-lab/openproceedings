# Highlights within the 50-hit page budget (2026-09-27, task-073)

Spec 03 §Performance budgets: a search returning the first 50 hits, p95 under 100 ms. The task-027 review
measured ~174 ms just to highlight a 50-hit page. This records the cost before and after task-073, on the
real local corpus, the 5k fixture and the synthetic 80k corpus, with the method, so it can be rerun.

- Machine: macOS-15.6.1-arm64, 8 CPUs; Python 3.12.9, tantivy 0.26.2; code: `dcdd129` plus task-073's change.
- **Not a quiet machine.** Other agents' test runs and a stray busy process held the 1-minute load average
  at 8–30 throughout (noted per table). Absolute numbers are therefore pessimistic. The before/after
  comparisons alternate the two versions round by round in one process, so load weighs on both alike;
  read the ratios with more confidence than the absolute times.

## What changed (spans unchanged)
- `query/normalize.py::tokenize`, which took three quarters of the time (cProfile, below), got two exact
  shortcuts: a whole text that is ASCII with no `\` and no `$` is its lower-cased `[A-Za-z0-9]+` runs (77%
  of real titles and abstracts; about 50% of the synthetic generator's), and in the character loop an ASCII
  character with no mark after it skips `_fold`. No `TOKENIZER_VERSION` bump: the tokens are identical.
- `engine/highlight.py`: one `Highlighter` per page (`search.run`) works out each leaf's allowed tokens
  once; per hit, a field is tokenized once and only if some leaf reads it, and a leaf's occurrences come
  from a map of where each token stands instead of a scan of the field per leaf.
- Nothing is precomputed at build or cached across requests; `engine/tantivy_engine.py`, `compile.py` and
  `api/` are untouched.

## Proof that no span changed
- `backend/tests/unit/engine/test_highlight_speed.py` checks the new code against frozen copies of the old
  (`tests/unit/tokenize_before.py`, `tests/unit/engine/highlight_before.py`): tokens equal in text, span,
  `op` and `reach` on arbitrary, ASCII and LaTeX-heavy Hypothesis text and on every text of both fixture
  corpora; highlight spans equal for all 44 golden queries on every record they match, every Trust-Evals
  string on the 5k corpus, generated trees over the 200-record fixture (all matches) and the 5k corpus (first
  20 matches each), and both refuse a non-hit the same way. Exact-span tests cover phrases (including one
  cut off by the field's end), wildcard-led phrases, both lookup branches, and NEAR in either order and with
  phrase and wildcard operands.
- The A/B scripts below assert old == new spans on every page before timing it.
- Real corpus: all 3,610 titles and abstracts tokenize identically (old vs new), and
  `op index parity --index a7cfd04b656f` (the index built with the old tokenizer, read-only) reports
  `"differences": 0` over 1,805 records. `OP_EXHAUSTIVE=1` (every code point in 8 contexts) passes.
- 12 hand mutants of the change: 11 killed; the survivor swaps which of two equivalent lookups
  `occurrences` uses (performance only, equivalent by construction).

## Profile (before; real index a7cfd04b656f, every Trust-Evals page highlighted once)
`tokenize` 2.15 s of 2.82 s (`_fold` 1.05 s over 413k calls, one per character); `occurrences` 0.64 s
(rescanning the field for every leaf). After: the remaining time is the loop on non-ASCII texts.

## Before / after: highlighting a 50-hit page (ms, p50 / p95)
Method: for each Trust-Evals string (Scholar mode), the engine's first 50 hits (fewer if the query matches
fewer) are highlighted by the old code (the frozen copies, per hit) and the new (one `Highlighter`), 100
rounds (40 at 80k), alternating. "Page" adds `search.run`'s own work (search, exclusion accounting, display
records), engine caches warm.

**Real local corpus** (index a7cfd04b656f, 1,805 records; load 25–28):

| String | Hits | Highlights before | after | Page before | after |
|---|---|---|---|---|---|
| main-1 | 36 | 141.9 / 145.9 | 19.9 / 20.5 | 143.7 / 146.4 | 22.8 / 23.5 |
| main-2-pop | 50 | 195.5 / 216.5 | 25.8 / 28.4 | 223.3 / 239.6 | 54.3 / 63.4 |
| main-3-sources | 36 | 142.5 / 162.4 | 19.9 / 23.8 | 144.9 / 180.2 | 23.1 / 23.8 |
| main-4-sources | 24 | 82.4 / 104.9 | 12.1 / 13.6 | 84.3 / 103.0 | 14.4 / 16.6 |
| main-5-sources | 19 | 63.0 / 66.9 | 8.8 / 10.2 | 65.2 / 70.5 | 11.0 / 13.2 |
| main-6-sources | 21 | 69.8 / 109.8 | 10.2 / 11.5 | 71.5 / 139.5 | 12.4 / 15.1 |
| main-7-most-updated | 21 | 70.1 / 72.4 | 10.2 / 10.9 | 71.8 / 74.7 | 12.4 / 12.8 |
| narrow | 24 | 82.0 / 180.1 | 12.1 / 18.1 | 83.9 / 174.7 | 14.1 / 15.0 |
| human-centered | 0 | 0.0 / 0.0 | 0.0 / 0.0 | 0.6 / 0.9 | 0.6 / 0.8 |
| llm-as-judge | 10 | 31.9 / 32.8 | 4.7 / 5.0 | 33.2 / 34.1 | 6.1 / 6.4 |

**5k fixture** (index 9c5ff9adb7b0, 8–60-word abstracts; load 24–28):

| String | Hits | Highlights before | after | Page before | after |
|---|---|---|---|---|---|
| main-1 | 50 | 43.7 / 52.0 | 8.0 / 8.3 | 47.4 / 78.3 | 11.8 / 12.9 |
| main-2-pop | 50 | 44.2 / 46.1 | 8.2 / 9.3 | 49.5 / 57.6 | 13.9 / 14.7 |
| main-3-sources | 50 | 43.4 / 46.1 | 8.0 / 8.6 | 47.4 / 52.1 | 12.3 / 15.6 |
| main-4-sources | 35 | 27.1 / 43.6 | 5.2 / 5.6 | 30.0 / 44.7 | 8.2 / 11.1 |
| main-5-sources | 29 | 31.7 / 81.9 | 4.9 / 20.3 | 35.4 / 74.0 | 8.8 / 25.9 |
| main-6-sources | 38 | 29.6 / 54.8 | 5.7 / 13.7 | 32.5 / 45.1 | 8.6 / 16.9 |
| main-7-most-updated | 38 | 29.0 / 34.5 | 5.7 / 6.6 | 31.9 / 35.6 | 8.5 / 9.2 |
| narrow | 35 | 27.3 / 37.2 | 5.3 / 7.0 | 29.8 / 35.7 | 8.0 / 10.4 |
| human-centered | 1 | 0.8 / 0.8 | 0.1 / 0.1 | 2.4 / 2.7 | 1.7 / 2.0 |
| llm-as-judge | 0 | 0.0 / 0.0 | 0.0 / 0.0 | 0.8 / 0.9 | 0.8 / 0.9 |

**Synthetic 80k** (`synthetic_5k.records(80000, (120, 250))`, the 80k report's corpus, index 27659e65468c;
load 16–23). "Page" here includes exclusion accounting, which has its own 300 ms budget; the last column
is the page without highlights, to show where the rest goes:

| String | Hits | Highlights before | after | Page before | after | Page without highlights |
|---|---|---|---|---|---|---|
| main-1 | 50 | 167.0 / 174.6 | 32.9 / 34.0 | 266.2 / 270.2 | 132.8 / 135.4 | 99.9 / 101.6 |
| main-2-pop | 50 | 169.5 / 172.8 | 33.2 / 34.2 | 245.2 / 250.5 | 110.0 / 112.0 | 76.1 / 78.2 |
| main-3-sources | 50 | 167.2 / 169.4 | 33.1 / 33.8 | 272.0 / 275.8 | 137.5 / 140.3 | 104.1 / 107.9 |
| main-4-sources | 50 | 138.1 / 140.8 | 31.3 / 32.1 | 213.0 / 217.1 | 106.5 / 107.7 | 75.0 / 76.9 |
| main-5-sources | 50 | 136.3 / 141.6 | 32.0 / 33.9 | 209.7 / 216.1 | 105.3 / 109.5 | 72.9 / 74.7 |
| main-6-sources | 50 | 143.4 / 161.4 | 32.7 / 34.8 | 196.4 / 210.0 | 88.0 / 95.6 | 54.7 / 63.2 |
| main-7-most-updated | 50 | 142.2 / 147.3 | 32.6 / 34.9 | 197.6 / 200.2 | 87.8 / 89.4 | 54.7 / 56.1 |
| narrow | 50 | 138.4 / 146.2 | 31.3 / 34.9 | 207.2 / 248.0 | 101.7 / 174.5 | 70.3 / 106.1 |
| human-centered | 50 | 128.1 / 130.4 | 32.4 / 35.4 | 201.9 / 212.7 | 106.0 / 110.2 | 73.4 / 81.7 |
| llm-as-judge | 0 | 0.0 / 0.0 | 0.0 / 0.0 | 1.5 / 1.8 | 1.5 / 1.9 | 1.5 / 2.4 |

## The budget at 80k (task-031's report, with the new column)
`uv run python -m tests.bench.report_80k <out>` at this change (load 8–14; written to a scratch path, not
over `2026-09-27-bench.md`, whose quiet-machine numbers stand). "Search with highlights" is
`test_bench.search_with_highlights`: the 50-hit search, its display records and every hit's highlights, as
`search.run` assembles them, less exclusion accounting (its own 300 ms budget) and facets; p95 of 200 warm
runs. Every string is inside 100 ms:

| String | Matches | Search, first 50 hits: cold | Search: p95 warm | Search with highlights: p95 warm | `match_ids` + exclusions: p95 cold |
|---|---|---|---|---|---|
| main-1 | 4,298 | 41.9 ms | 35.0 ms | 73.2 ms | 108.8 ms |
| main-2-pop | 4,417 | 10,534.8 ms | 29.8 ms | 64.2 ms | 11,985.7 ms |
| main-3-sources | 4,298 | 41.9 ms | 35.9 ms | 70.8 ms | 104.5 ms |
| main-4-sources | 3,980 | 29.4 ms | 25.5 ms | 59.8 ms | 76.5 ms |
| main-5-sources | 3,907 | 23.5 ms | 24.3 ms | 58.6 ms | 73.9 ms |
| main-6-sources | 4,062 | 17.8 ms | 18.5 ms | 54.4 ms | 55.9 ms |
| main-7-most-updated | 4,062 | 18.2 ms | 18.5 ms | 53.0 ms | 59.0 ms |
| narrow | 3,980 | 23.8 ms | 24.9 ms | 58.2 ms | 70.7 ms |
| human-centered | 278 | 28.8 ms | 25.2 ms | 61.4 ms | 77.3 ms |
| llm-as-judge | 0 | 1.7 ms | 0.8 ms | 0.7 ms | 2.1 ms |

Before this change the same column would be the warm search plus 128–175 ms of highlighting (the 80k table
above): about 155–210 ms, over budget. `main-2-pop`'s cold numbers are spec 03's position-verified exception.
The same run's index build took 21.9 s (30.3 s in `2026-09-27-bench.md`): the build tokenizes every record,
so it gains from the tokenizer's shortcuts too.

## Fixture benchmark (the `bench` workflow's row)
`uv run pytest backend/tests/bench --benchmark-enable --benchmark-only -k first_50_hits` (load 11):
`test_search_first_50_hits_with_highlights` medians 0.3–10.8 ms (main-2-pop the largest), against
`test_search_first_50_hits` 0.3–1.6 ms; all under the 100 ms p95 assertion.

## Reproduce
The A/B and profiling scripts were scratch (not committed); the committed equivalents are the differential
tests above, the bench row and the 80k report column. To rerun the A/B: time
`tests.unit.engine.highlight_before.highlights` per hit against one `engine.highlight.Highlighter` per page
over `engine.page(ast, limit=50)`, alternating rounds, after asserting equal output.
