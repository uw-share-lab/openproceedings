# What group counts add to a search (2026-10-10)

Regenerate with `uv run python -m tests.bench.group_counts_report --index <a copy of an index>` (from
`backend/`, on a quiet machine: other load inflates the timings); never edit by hand. TASK-176; cited by spec
04 §SearchResponse (`groups`, Cost) and spec 07 §E. Spec 03's 100 ms p95 budget covers a cold first page with
its counts (decision-039, TASK-197). A run is cited only when its 1-minute load (below) is under 5 at the start
and the end.

- Machine: Apple M1 Pro, macOS-15.6.1-arm64-arm-64bit, 8 CPUs; load average 4.2 / 4.2 / 6.1 at the
  start and 5.3 / 5.0 / 5.9 at the end (1, 5, 15 min); Python 3.12.15, tantivy
  0.26.2; commit `673112f6`.
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
| `(trust OR reliance) AND calibrat* AND model*` | 88 | first page | 8.2 ms | 8.8 ms | 20.6 ms | 35.3 ms | 3 counted ×200 |
| `(trust OR reliance) AND calibrat* AND model*` | 88 | later page | 6.3 ms | 6.8 ms | 10.9 ms | 11.6 ms | 3 counted ×200 |
| `trust model NOT (model NEAR/10 model*)` | 30 | first page | 5.7 ms | 5.9 ms | 9.8 ms | 10.9 ms | 2 counted ×200 |
| `trust model NOT (model NEAR/10 model*)` | 30 | later page | 1.3 ms | 1.6 ms | 3.5 ms | 3.8 ms | 2 counted ×200 |
| `agent ai benchmark calibration language bias dataset human trust model` | 0 | first page | 1.2 ms | 1.5 ms | 26.1 ms | 40.7 ms | 10 counted ×200 |
| `agent ai benchmark calibration language bias dataset human trust model` | 0 | later page | 0.7 ms | 0.9 ms | 8.0 ms | 9.1 ms | 10 counted ×200 |
| `trust model data learning neural network training language agent task NOT (… 158 wildcards …)` | 0 | first page | 30.0 ms | 34.4 ms | 30.1 ms | 35.0 ms | too_costly ×200 |
| `trust model data learning neural network training language agent task NOT (… 158 wildcards …)` | 0 | later page | 28.5 ms | 29.7 ms | 28.5 ms | 30.0 ms | too_costly ×200 |

## The real corpus: index `757641db0a20`, 166,759 records

| Query | Matches | Page | Without counts: median | p95 | With counts: median | p95 | Groups, per round |
|---|---|---|---|---|---|---|---|
| `(trust OR reliance) AND calibrat* AND model*` | 58 | first page | 19.0 ms | 19.6 ms | 30.4 ms | 31.1 ms | 3 counted ×200 |
| `(trust OR reliance) AND calibrat* AND model*` | 58 | later page | 8.6 ms | 9.1 ms | 8.6 ms | 9.2 ms | 3 counted ×200 |
| `("large language model$" OR LLM*) AND (trust* OR calibrat*) AND (benchmark* OR evaluat*)` | 390 | first page | 34.9 ms | 36.3 ms | 56.1 ms | 58.5 ms | 3 counted ×200 |
| `("large language model$" OR LLM*) AND (trust* OR calibrat*) AND (benchmark* OR evaluat*)` | 390 | later page | 32.6 ms | 33.9 ms | 32.7 ms | 33.8 ms | 3 counted ×200 |
| `trust model NOT (model NEAR/10 model*)` | 211 | first page | 30.4 ms | 33.5 ms | 54.0 ms | 56.1 ms | 2 counted ×200 |
| `trust model NOT (model NEAR/10 model*)` | 211 | later page | 26.0 ms | 27.2 ms | 26.0 ms | 27.1 ms | 2 counted ×200 |
| `trust model data learning neural network training language agent task` | 0 | first page | 3.2 ms | 3.9 ms | 42.0 ms | 58.6 ms | 10 counted ×200 |
| `trust model data learning neural network training language agent task` | 0 | later page | 2.8 ms | 3.4 ms | 3.1 ms | 3.4 ms | 10 counted ×200 |

### Every Trust-Evals string (`tests/golden/test_trust_evals.py`, Scholar syntax), as the API serves it

| Query | Matches | Page | Without counts: median | p95 | With counts: median | p95 | Groups, per round |
|---|---|---|---|---|---|---|---|
| `main-1` | 100 | first page | 26.1 ms | 27.3 ms | 43.9 ms | 47.9 ms | 3 counted ×200 |
| `main-1` | 100 | later page | 24.6 ms | 25.5 ms | 24.6 ms | 25.6 ms | 3 counted ×200 |
| `main-2-pop` | 164 | first page | 65.5 ms | 67.6 ms | 82.5 ms | 85.2 ms | 3 counted ×200 |
| `main-2-pop` | 164 | later page | 65.5 ms | 67.2 ms | 65.6 ms | 67.4 ms | 3 counted ×200 |
| `main-3-sources` | 68 | first page | 27.3 ms | 28.3 ms | 45.0 ms | 46.4 ms | 3 counted ×200 |
| `main-3-sources` | 68 | later page | 16.4 ms | 17.4 ms | 16.5 ms | 17.3 ms | 3 counted ×200 |
| `main-4-sources` | 30 | first page | 16.8 ms | 17.6 ms | 29.4 ms | 30.1 ms | 3 counted ×200 |
| `main-4-sources` | 30 | later page | 7.2 ms | 7.9 ms | 7.2 ms | 7.9 ms | 3 counted ×200 |
| `main-5-sources` | 22 | first page | 14.1 ms | 15.1 ms | 26.1 ms | 27.0 ms | 3 counted ×200 |
| `main-5-sources` | 22 | later page | 6.9 ms | 7.6 ms | 7.0 ms | 7.6 ms | 3 counted ×200 |
| `main-6-sources` | 33 | first page | 17.3 ms | 18.2 ms | 28.4 ms | 29.2 ms | 3 counted ×200 |
| `main-6-sources` | 33 | later page | 6.9 ms | 7.4 ms | 6.9 ms | 7.4 ms | 3 counted ×200 |
| `main-7-most-updated` | 33 | first page | 17.3 ms | 18.0 ms | 28.4 ms | 29.4 ms | 3 counted ×200 |
| `main-7-most-updated` | 33 | later page | 6.8 ms | 7.3 ms | 6.9 ms | 7.5 ms | 3 counted ×200 |
| `narrow` | 46 | first page | 20.1 ms | 20.9 ms | 31.2 ms | 32.3 ms | 3 counted ×200 |
| `narrow` | 46 | later page | 6.7 ms | 7.2 ms | 6.8 ms | 7.4 ms | 3 counted ×200 |
| `human-centered` | 6 | first page | 4.2 ms | 4.8 ms | 5.6 ms | 5.9 ms | 2 counted ×200 |
| `human-centered` | 6 | later page | 2.2 ms | 2.6 ms | 2.2 ms | 2.6 ms | 2 counted ×200 |
| `llm-as-judge` | 44 | first page | 14.4 ms | 15.4 ms | 18.9 ms | 19.7 ms | 3 counted ×200 |
| `llm-as-judge` | 44 | later page | 2.6 ms | 3.0 ms | 2.6 ms | 3.1 ms | 3 counted ×200 |
