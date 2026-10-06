# What group counts add to a search (2026-10-06)

Regenerate with `uv run python -m tests.bench.group_counts_report --index <a copy of an index>` (from
`backend/`, on a quiet machine: other load inflates the timings); never edit by hand. TASK-176; cited by spec
04 §SearchResponse (`groups`, Cost) and spec 07 §E. Spec 03's 100 ms p95 budget covers a cold first page with
its counts (decision-039, TASK-197). A run is cited only when its 1-minute load (below) is under 5 at the start
and the end.

- Machine: Apple M1 Pro, macOS-15.6.1-arm64-arm-64bit, 8 CPUs; load average 3.4 / 6.6 / 13.0 at the
  start and 4.6 / 5.4 / 10.6 at the end (1, 5, 15 min); Python 3.12.9, tantivy
  0.26.2; commit `66613463`.
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
| `(trust OR reliance) AND calibrat* AND model*` | 88 | first page | 8.4 ms | 9.0 ms | 20.8 ms | 36.1 ms | 3 counted ×200 |
| `(trust OR reliance) AND calibrat* AND model*` | 88 | later page | 6.4 ms | 7.0 ms | 11.0 ms | 11.9 ms | 3 counted ×200 |
| `trust model NOT (model NEAR/10 model*)` | 30 | first page | 5.8 ms | 6.4 ms | 9.9 ms | 11.5 ms | 2 counted ×200 |
| `trust model NOT (model NEAR/10 model*)` | 30 | later page | 1.3 ms | 1.5 ms | 3.5 ms | 3.8 ms | 2 counted ×200 |
| `agent ai benchmark calibration language bias dataset human trust model` | 0 | first page | 1.2 ms | 1.5 ms | 26.2 ms | 41.4 ms | 10 counted ×200 |
| `agent ai benchmark calibration language bias dataset human trust model` | 0 | later page | 0.7 ms | 0.8 ms | 7.9 ms | 8.9 ms | 10 counted ×200 |
| `trust model data learning neural network training language agent task NOT (… 158 wildcards …)` | 0 | first page | 30.2 ms | 35.3 ms | 30.1 ms | 35.2 ms | too_costly ×200 |
| `trust model data learning neural network training language agent task NOT (… 158 wildcards …)` | 0 | later page | 28.0 ms | 29.6 ms | 28.1 ms | 29.6 ms | too_costly ×200 |

## The real corpus: index `fd13d8d27535`, 133,629 records

| Query | Matches | Page | Without counts: median | p95 | With counts: median | p95 | Groups, per round |
|---|---|---|---|---|---|---|---|
| `(trust OR reliance) AND calibrat* AND model*` | 45 | first page | 16.8 ms | 17.5 ms | 22.9 ms | 23.7 ms | 3 counted ×200 |
| `(trust OR reliance) AND calibrat* AND model*` | 45 | later page | 4.6 ms | 5.1 ms | 4.7 ms | 5.1 ms | 3 counted ×200 |
| `("large language model$" OR LLM*) AND (trust* OR calibrat*) AND (benchmark* OR evaluat*)` | 310 | first page | 33.0 ms | 45.8 ms | 50.7 ms | 53.7 ms | 3 counted ×200 |
| `("large language model$" OR LLM*) AND (trust* OR calibrat*) AND (benchmark* OR evaluat*)` | 310 | later page | 30.7 ms | 33.2 ms | 30.7 ms | 32.8 ms | 3 counted ×200 |
| `trust model NOT (model NEAR/10 model*)` | 143 | first page | 27.7 ms | 30.3 ms | 33.7 ms | 40.5 ms | 2 counted ×200 |
| `trust model NOT (model NEAR/10 model*)` | 143 | later page | 23.1 ms | 24.9 ms | 23.2 ms | 25.1 ms | 2 counted ×200 |
| `trust model data learning neural network training language agent task` | 0 | first page | 2.4 ms | 3.0 ms | 30.0 ms | 33.9 ms | 10 counted ×200 |
| `trust model data learning neural network training language agent task` | 0 | later page | 2.1 ms | 2.3 ms | 2.1 ms | 2.4 ms | 10 counted ×200 |

### Every Trust-Evals string (`tests/golden/test_trust_evals.py`, Scholar syntax), as the API serves it

| Query | Matches | Page | Without counts: median | p95 | With counts: median | p95 | Groups, per round |
|---|---|---|---|---|---|---|---|
| `main-1` | 68 | first page | 25.7 ms | 27.9 ms | 40.3 ms | 46.1 ms | 3 counted ×200 |
| `main-1` | 68 | later page | 14.4 ms | 15.2 ms | 14.5 ms | 15.5 ms | 3 counted ×200 |
| `main-2-pop` | 114 | first page | 60.2 ms | 65.6 ms | 73.8 ms | 85.4 ms | 3 counted ×200 |
| `main-2-pop` | 114 | later page | 59.2 ms | 64.5 ms | 59.3 ms | 61.7 ms | 3 counted ×200 |
| `main-3-sources` | 68 | first page | 26.4 ms | 29.3 ms | 40.5 ms | 44.5 ms | 3 counted ×200 |
| `main-3-sources` | 68 | later page | 14.9 ms | 15.6 ms | 15.0 ms | 15.7 ms | 3 counted ×200 |
| `main-4-sources` | 30 | first page | 16.0 ms | 16.7 ms | 25.7 ms | 26.9 ms | 3 counted ×200 |
| `main-4-sources` | 30 | later page | 6.2 ms | 6.6 ms | 6.3 ms | 6.7 ms | 3 counted ×200 |
| `main-5-sources` | 22 | first page | 13.2 ms | 13.8 ms | 23.6 ms | 24.3 ms | 3 counted ×200 |
| `main-5-sources` | 22 | later page | 5.9 ms | 6.4 ms | 6.0 ms | 6.4 ms | 3 counted ×200 |
| `main-6-sources` | 33 | first page | 16.7 ms | 17.5 ms | 26.0 ms | 27.0 ms | 3 counted ×200 |
| `main-6-sources` | 33 | later page | 5.9 ms | 6.4 ms | 6.0 ms | 6.4 ms | 3 counted ×200 |
| `main-7-most-updated` | 33 | first page | 16.7 ms | 17.8 ms | 26.0 ms | 27.1 ms | 3 counted ×200 |
| `main-7-most-updated` | 33 | later page | 5.9 ms | 6.3 ms | 6.0 ms | 6.3 ms | 3 counted ×200 |
| `narrow` | 30 | first page | 15.4 ms | 16.3 ms | 25.2 ms | 26.4 ms | 3 counted ×200 |
| `narrow` | 30 | later page | 5.7 ms | 6.1 ms | 5.7 ms | 6.0 ms | 3 counted ×200 |
| `human-centered` | 4 | first page | 3.2 ms | 3.6 ms | 4.0 ms | 5.0 ms | 2 counted ×200 |
| `human-centered` | 4 | later page | 1.7 ms | 2.0 ms | 1.7 ms | 2.0 ms | 2 counted ×200 |
| `llm-as-judge` | 38 | first page | 13.1 ms | 13.8 ms | 16.4 ms | 17.3 ms | 3 counted ×200 |
| `llm-as-judge` | 38 | later page | 2.2 ms | 2.5 ms | 2.2 ms | 2.5 ms | 3 counted ×200 |
