# What group counts add to a search (2026-10-05)

Regenerate with `uv run python -m tests.bench.group_counts_report --index <a copy of an index>` (from
`backend/`, on a quiet machine: other load inflates the timings); never edit by hand. TASK-176; cited by spec
04 §SearchResponse (`groups`, Cost) and spec 07 §E.

- Machine: Apple M1 Pro, macOS-15.6.1-arm64-arm-64bit, 8 CPUs; load average 4.5 / 17.9 / 28.6 at the
  start and 9.8 / 14.8 / 25.7 at the end (1, 5, 15 min); Python 3.12.9, tantivy
  0.26.2; commit `c41ea508`.
- Protocol: `search.run` with facets and highlights, a 50-hit page, as `/search` runs it
  (`tests/bench/test_bench.py::search_endpoint`), with its groups counted at `ApiConfig`'s defaults
  (`groups` 10, `groups_terms` 5000, `groups_ids` 300000, `groups_wait` 2.0, `groups_grace` 0.05) and without them, alternated within each of 200 rounds after one warm-up; wall time (the
  facets and the counts run on worker threads, overlapping the page). A first page forgets the facet memo
  every round, so its counts' collections are made again; a later page (offset 50) reads them from the memo.
  "Groups, per round" is how each round's groups came back: counted, or the `not_counted` reason.

## The synthetic 5k fixture, as the API serves it

The last query is ten one-word groups and one kept `NOT (… every three-letter wildcard under the cap …)`
(`tests/unit/test_group_counts.py::wide_kept_query`): over `max_counted_terms`, so `too_costly` and never
counted.

| Query | Matches | Page | Without counts: median | p95 | With counts: median | p95 | Groups, per round |
|---|---|---|---|---|---|---|---|
| `(trust OR reliance) AND calibrat* AND model*` | 88 | first page | 8.4 ms | 8.9 ms | 20.8 ms | 35.7 ms | 3 counted ×200 |
| `(trust OR reliance) AND calibrat* AND model*` | 88 | later page | 6.6 ms | 7.2 ms | 11.2 ms | 11.9 ms | 3 counted ×200 |
| `trust model NOT (model NEAR/10 model*)` | 30 | first page | 5.8 ms | 6.4 ms | 10.1 ms | 11.3 ms | 2 counted ×200 |
| `trust model NOT (model NEAR/10 model*)` | 30 | later page | 1.4 ms | 1.6 ms | 3.4 ms | 3.8 ms | 2 counted ×200 |
| `agent ai benchmark calibration language bias dataset human trust model` | 0 | first page | 1.3 ms | 4.7 ms | 27.3 ms | 44.7 ms | 10 counted ×200 |
| `agent ai benchmark calibration language bias dataset human trust model` | 0 | later page | 0.8 ms | 1.0 ms | 8.1 ms | 8.9 ms | 10 counted ×200 |
| `trust model data learning neural network training language agent task NOT (… 158 wildcards …)` | 0 | first page | 31.0 ms | 37.9 ms | 31.0 ms | 40.5 ms | too_costly ×200 |
| `trust model data learning neural network training language agent task NOT (… 158 wildcards …)` | 0 | later page | 29.1 ms | 30.8 ms | 29.1 ms | 31.1 ms | too_costly ×200 |

## The real corpus: index `fd13d8d27535`, 133,629 records

| Query | Matches | Page | Without counts: median | p95 | With counts: median | p95 | Groups, per round |
|---|---|---|---|---|---|---|---|
| `(trust OR reliance) AND calibrat* AND model*` | 45 | first page | 17.2 ms | 19.2 ms | 23.8 ms | 28.9 ms | 3 counted ×200 |
| `(trust OR reliance) AND calibrat* AND model*` | 45 | later page | 4.8 ms | 5.3 ms | 4.9 ms | 5.5 ms | 3 counted ×200 |
| `("large language model$" OR LLM*) AND (trust* OR calibrat*) AND (benchmark* OR evaluat*)` | 310 | first page | 34.3 ms | 50.6 ms | 80.2 ms | 110.8 ms | 3 counted ×200 |
| `("large language model$" OR LLM*) AND (trust* OR calibrat*) AND (benchmark* OR evaluat*)` | 310 | later page | 32.3 ms | 47.9 ms | 32.3 ms | 38.8 ms | 3 counted ×200 |
| `trust model NOT (model NEAR/10 model*)` | 143 | first page | 29.6 ms | 39.3 ms | 47.7 ms | 63.4 ms | 2 counted ×200 |
| `trust model NOT (model NEAR/10 model*)` | 143 | later page | 24.5 ms | 31.1 ms | 24.5 ms | 33.3 ms | 2 counted ×200 |
| `trust model data learning neural network training language agent task` | 0 | first page | 2.4 ms | 5.0 ms | 30.6 ms | 44.5 ms | 10 counted ×200 |
| `trust model data learning neural network training language agent task` | 0 | later page | 2.1 ms | 2.4 ms | 2.2 ms | 2.4 ms | 10 counted ×200 |
