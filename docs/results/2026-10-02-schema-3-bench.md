# Benchmarks on a synthetic ~80k corpus (2026-10-03)

Regenerate with `uv run python -m tests.bench.report_80k` (from `backend/`, on a quiet machine: other load
inflates the timings); never edit by hand. Budgets are
spec 03 §Performance budgets. Position-verified clauses are exempt from the search and `match_ids` budgets
when cold (spec 03), so they are reported, not gated.

- Machine: macOS-15.6.1-arm64-arm-64bit, arm64, 8 CPUs, load average 5.1 / 5.9 / 6.8 at
  the start and 3.2 / 5.6 / 6.4 at the end (1, 5, 15 min); Python 3.12.9,
  tantivy 0.26.2; commit `ace8a1de`; index `83f44f4eb82f`.
- Corpus: `tests/fixtures/corpus/synthetic_5k.records(80000, (120, 250))`, 80,000 records (generated in
  7.0 s): the differential corpus's generator with abstracts of 120-250 words.

## Build (budget: under 2 min, under 500 MB)

| Build time | Index size | Peak memory: the largest single process (the build; its ~65 MB workers are not summed) |
|---|---|---|
| 14.3 s | 99 MB | 409 MB |

## Trust-Evals protocol strings, Scholar mode (budgets: 100 ms, 300 ms)

Cold is the first run after every engine cache is cleared (verified clauses, expansions, compiled queries,
facet combinations and the lazy id-to-ordinal table); the open index and OS page cache stay warm. Warm is the
p95 and the p99 of the 200 runs after it, with the caches an engine keeps; "with highlights" is the p95 of
200 warm runs of the same search with its display records and every hit's highlights, as
`search.run` assembles them (`test_bench.search_with_highlights`; no cache holds them; task-073); the two
`/search` columns are the endpoint's whole engine work (`test_bench.search_endpoint`: `search.run` with facets,
highlights and exclusion accounting; its facet aggregation on a worker thread, overlapping the page), p95 of
200 runs in wall time: the first page with the facet memo forgotten each run, and a later page
(offset 50) that reads it; then the first page's mean CPU time per request over 200 more runs (all
threads: the overlap saves wall time, not CPU); the exclusions column is the p95 of
40 runs, each clearing those engine caches first, using only track/status aggregation (`over=ORDER`),
as exclusion-only callers do. Older reports aggregated every facet and retained some caches; their cold column
is not directly comparable. `main-2-pop` holds wildcard phrases (`model$`), which take the position-verified path spec 03 exempts, so
its cold numbers are the exception's, not a budget miss (task-076 is its warm headroom).

| String | Matches | Search, first 50 hits: cold | Search: p95 warm | Search: p99 warm | Search with highlights: p95 warm | `/search`, first page: p95 wall | `/search`, a later page: p95 wall | `/search`, first page: CPU per request | `match_ids` + exclusions: p95 cold |
|---|---|---|---|---|---|---|---|---|---|
| main-1 | 4,298 | 40.1 ms | 34.2 ms | 61.4 ms | 57.8 ms | 68.8 ms | 59.8 ms | 92.0 ms | 70.5 ms |
| main-2-pop | 4,417 | 9,625.3 ms | 26.4 ms | 29.0 ms | 47.3 ms | 61.4 ms | 51.4 ms | 83.0 ms | 17,095.6 ms |
| main-3-sources | 4,298 | 41.2 ms | 35.5 ms | 43.7 ms | 55.2 ms | 74.9 ms | 64.3 ms | 91.9 ms | 71.6 ms |
| main-4-sources | 3,980 | 25.8 ms | 26.0 ms | 31.0 ms | 44.3 ms | 48.8 ms | 47.2 ms | 70.8 ms | 51.5 ms |
| main-5-sources | 3,907 | 23.3 ms | 23.8 ms | 25.2 ms | 44.3 ms | 54.1 ms | 44.7 ms | 70.1 ms | 46.6 ms |
| main-6-sources | 4,062 | 19.0 ms | 19.4 ms | 22.5 ms | 55.3 ms | 51.7 ms | 41.0 ms | 58.5 ms | 70.8 ms |
| main-7-most-updated | 4,062 | 17.2 ms | 17.5 ms | 18.3 ms | 37.1 ms | 41.2 ms | 37.7 ms | 57.2 ms | 35.2 ms |
| narrow | 3,980 | 22.9 ms | 23.5 ms | 24.7 ms | 42.7 ms | 47.5 ms | 43.7 ms | 69.2 ms | 46.0 ms |
| human-centered | 278 | 27.3 ms | 24.4 ms | 26.1 ms | 43.6 ms | 48.3 ms | 45.6 ms | 69.9 ms | 47.5 ms |
| llm-as-judge | 0 | 1.7 ms | 0.8 ms | 1.4 ms | 0.7 ms | 0.8 ms | 0.8 ms | 1.2 ms | 1.2 ms |

## Wildcard expansion (budget: 50 ms for up to 200 terms)

| Stem | Terms | p95 |
|---|---|---|
| `ren*` | 124 | 0.1 ms |
| `co*` (past the cap: refused) | 1200 distinct | 0.9 ms |

## Position-verified clauses (the spec 03 exception; one cold run each)

| Query | Matches | `match_ids` |
|---|---|---|
| `the NEAR/5 the` | 473 | 2,726.9 ms |
| `"the*" NEAR/5 model` | 1,036 | 2,128.9 ms |
| `"of the" NEAR/3 model*` | 149 | 2,166.3 ms |
| `"a model*"` | 1,072 | 3,181.7 ms |
| `"large language model$"` | 30 | 2,222.0 ms |
| `trust NEAR/0 trust` | 238 | 2,678.3 ms |

## Over budget

Nothing: every budgeted number above is within its budget.
