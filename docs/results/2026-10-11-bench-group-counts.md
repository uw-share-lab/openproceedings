# What group counts add to a search (2026-10-11)

Regenerate with `uv run python -m tests.bench.group_counts_report --index <a copy of an index>` (from
`backend/`, on a quiet machine: other load inflates the timings); never edit by hand. TASK-176; cited by spec
04 §SearchResponse (`groups`, Cost) and spec 07 §E. Spec 03's 100 ms p95 budget covers a cold first page with
its counts (decision-039, TASK-197). A run is cited only when its 1-minute load (below) is under 5 at the start
and the end.

- Machine: Apple M1 Pro, macOS-15.6.1-arm64-arm-64bit, 8 CPUs; load average 2.6 / 4.5 / 4.5 at the
  start and 4.0 / 4.3 / 4.4 at the end (1, 5, 15 min); Python 3.12.15, tantivy
  0.26.2; commit `4ece1d98`.
- Protocol: `search.run` with facets and highlights, a 50-hit page, as `/search` runs it
  (`tests/bench/test_bench.py::search_endpoint`), with its groups counted at `ApiConfig`'s defaults
  (`max_counted_groups` 10, `max_counted_terms` 5000, `max_counted_ids` 300000, `group_count_wait_seconds` 2.0, `group_count_grace_seconds` 0.05) and without them, alternated within each of 200 rounds after one warm-up; wall time (the
  facets and the counts run on worker threads, overlapping the page). A first page forgets the facet memo
  every round, so its counts' collections are made again; a later page (offset 50) reads them from the memo.
  "Groups, per round" is how each round's groups came back: counted, or the `not_counted` reason.

## The synthetic 5k fixture, as the API serves it

The last query is ten one-word groups and one kept `NOT (… every three-letter wildcard under the cap …)`
(`tests/unit/test_group_counts.py::wide_kept_query`): over `max_counted_terms`, so `too_costly` and never
counted.

| Query | Matches | Page | Without counts: median | p95 | With counts: median | p95 | Groups, per round |
|---|---|---|---|---|---|---|---|
| `(trust OR reliance) AND calibrat* AND model*` | 88 | first page | 8.7 ms | 9.2 ms | 9.5 ms | 9.9 ms | 3 counted ×200 |
| `(trust OR reliance) AND calibrat* AND model*` | 88 | later page | 6.4 ms | 7.1 ms | 6.8 ms | 7.5 ms | 3 counted ×200 |
| `trust model NOT (model NEAR/10 model*)` | 30 | first page | 5.9 ms | 6.3 ms | 6.7 ms | 7.1 ms | 2 counted ×200 |
| `trust model NOT (model NEAR/10 model*)` | 30 | later page | 1.3 ms | 1.4 ms | 1.6 ms | 1.7 ms | 2 counted ×200 |
| `agent ai benchmark calibration language bias dataset human trust model` | 0 | first page | 0.7 ms | 0.8 ms | 3.6 ms | 4.0 ms | 10 counted ×200 |
| `agent ai benchmark calibration language bias dataset human trust model` | 0 | later page | 0.6 ms | 0.7 ms | 1.3 ms | 1.5 ms | 10 counted ×200 |
| `trust model data learning neural network training language agent task NOT (… 158 wildcards …)` | 0 | first page | 28.5 ms | 30.7 ms | 28.5 ms | 31.3 ms | too_costly ×200 |
| `trust model data learning neural network training language agent task NOT (… 158 wildcards …)` | 0 | later page | 27.5 ms | 29.4 ms | 27.5 ms | 29.4 ms | too_costly ×200 |

## The real corpus: index `b4f335e07e70`, 173,253 records

| Query | Matches | Page | Without counts: median | p95 | With counts: median | p95 | Groups, per round |
|---|---|---|---|---|---|---|---|
| `(trust OR reliance) AND calibrat* AND model*` | 60 | first page | 18.5 ms | 19.2 ms | 18.7 ms | 19.8 ms | 3 counted ×200 |
| `(trust OR reliance) AND calibrat* AND model*` | 60 | later page | 8.7 ms | 9.4 ms | 8.7 ms | 9.4 ms | 3 counted ×200 |
| `("large language model$" OR LLM*) AND (trust* OR calibrat*) AND (benchmark* OR evaluat*)` | 399 | first page | 33.7 ms | 35.0 ms | 34.6 ms | 36.1 ms | 3 counted ×200 |
| `("large language model$" OR LLM*) AND (trust* OR calibrat*) AND (benchmark* OR evaluat*)` | 399 | later page | 31.4 ms | 32.7 ms | 31.5 ms | 32.5 ms | 3 counted ×200 |
| `trust model NOT (model NEAR/10 model*)` | 234 | first page | 27.8 ms | 31.3 ms | 43.4 ms | 47.3 ms | 2 counted ×200 |
| `trust model NOT (model NEAR/10 model*)` | 234 | later page | 25.2 ms | 26.7 ms | 25.4 ms | 26.6 ms | 2 counted ×200 |
| `trust model data learning neural network training language agent task` | 0 | first page | 2.8 ms | 3.1 ms | 12.3 ms | 12.6 ms | 10 counted ×200 |
| `trust model data learning neural network training language agent task` | 0 | later page | 2.5 ms | 2.8 ms | 2.6 ms | 2.9 ms | 10 counted ×200 |

### Every Trust-Evals string (`tests/golden/test_trust_evals.py`, Scholar syntax), as the API serves it

| Query | Matches | Page | Without counts: median | p95 | With counts: median | p95 | Groups, per round |
|---|---|---|---|---|---|---|---|
| `main-1` | 103 | first page | 25.2 ms | 26.3 ms | 25.7 ms | 26.6 ms | 3 counted ×200 |
| `main-1` | 103 | later page | 23.4 ms | 24.6 ms | 23.5 ms | 24.9 ms | 3 counted ×200 |
| `main-2-pop` | 169 | first page | 63.8 ms | 65.6 ms | 65.8 ms | 67.4 ms | 3 counted ×200 |
| `main-2-pop` | 169 | later page | 63.8 ms | 65.4 ms | 64.0 ms | 65.8 ms | 3 counted ×200 |
| `main-3-sources` | 68 | first page | 26.9 ms | 27.8 ms | 27.4 ms | 29.0 ms | 3 counted ×200 |
| `main-3-sources` | 68 | later page | 15.8 ms | 16.9 ms | 15.9 ms | 17.0 ms | 3 counted ×200 |
| `main-4-sources` | 30 | first page | 16.0 ms | 17.0 ms | 16.3 ms | 17.2 ms | 3 counted ×200 |
| `main-4-sources` | 30 | later page | 6.9 ms | 7.4 ms | 7.0 ms | 7.5 ms | 3 counted ×200 |
| `main-5-sources` | 22 | first page | 13.3 ms | 14.3 ms | 13.8 ms | 14.8 ms | 3 counted ×200 |
| `main-5-sources` | 22 | later page | 6.6 ms | 7.1 ms | 6.6 ms | 7.2 ms | 3 counted ×200 |
| `main-6-sources` | 33 | first page | 16.7 ms | 17.7 ms | 17.0 ms | 17.9 ms | 3 counted ×200 |
| `main-6-sources` | 33 | later page | 6.7 ms | 7.1 ms | 6.7 ms | 7.3 ms | 3 counted ×200 |
| `main-7-most-updated` | 33 | first page | 16.7 ms | 17.6 ms | 16.9 ms | 17.9 ms | 3 counted ×200 |
| `main-7-most-updated` | 33 | later page | 6.6 ms | 7.1 ms | 6.7 ms | 7.3 ms | 3 counted ×200 |
| `narrow` | 46 | first page | 19.3 ms | 20.5 ms | 19.5 ms | 20.4 ms | 3 counted ×200 |
| `narrow` | 46 | later page | 6.5 ms | 7.0 ms | 6.5 ms | 7.1 ms | 3 counted ×200 |
| `human-centered` | 10 | first page | 5.5 ms | 6.0 ms | 5.7 ms | 6.0 ms | 2 counted ×200 |
| `human-centered` | 10 | later page | 2.2 ms | 2.5 ms | 2.2 ms | 2.5 ms | 2 counted ×200 |
| `llm-as-judge` | 47 | first page | 15.5 ms | 16.3 ms | 15.7 ms | 16.5 ms | 3 counted ×200 |
| `llm-as-judge` | 47 | later page | 2.5 ms | 2.8 ms | 2.6 ms | 2.8 ms | 3 counted ×200 |
