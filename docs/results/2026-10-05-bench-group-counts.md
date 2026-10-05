# What group counts add to a search (2026-10-05)

Regenerate with `uv run python -m tests.bench.group_counts_report --index <a copy of an index>` (from
`backend/`, on a quiet machine: other load inflates the timings); never edit by hand. TASK-176; cited by spec
04 §SearchResponse (`groups`, Cost) and spec 07 §E. A cold first page over spec 03's 100 ms p95 with its counts
is spec 03's exception "as measured" (decision-039; TASK-197 brings it under), measured at a 1-minute load under 5.

- Machine: Apple M1 Pro, macOS-15.6.1-arm64-arm-64bit, 8 CPUs; load average 3.9 / 4.4 / 6.9 at the
  start and 3.3 / 4.6 / 6.3 at the end (1, 5, 15 min); Python 3.12.9, tantivy
  0.26.2; commit `bed0a6cb-dirty`.
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
| `(trust OR reliance) AND calibrat* AND model*` | 88 | first page | 8.1 ms | 9.0 ms | 20.2 ms | 34.7 ms | 3 counted ×200 |
| `(trust OR reliance) AND calibrat* AND model*` | 88 | later page | 6.2 ms | 6.9 ms | 10.7 ms | 11.9 ms | 3 counted ×200 |
| `trust model NOT (model NEAR/10 model*)` | 30 | first page | 5.8 ms | 12.0 ms | 10.0 ms | 24.4 ms | 2 counted ×200 |
| `trust model NOT (model NEAR/10 model*)` | 30 | later page | 1.3 ms | 1.9 ms | 3.6 ms | 4.9 ms | 2 counted ×200 |
| `agent ai benchmark calibration language bias dataset human trust model` | 0 | first page | 1.3 ms | 2.2 ms | 26.2 ms | 42.2 ms | 10 counted ×200 |
| `agent ai benchmark calibration language bias dataset human trust model` | 0 | later page | 0.6 ms | 0.8 ms | 7.8 ms | 8.8 ms | 10 counted ×200 |
| `trust model data learning neural network training language agent task NOT (… 158 wildcards …)` | 0 | first page | 29.3 ms | 33.7 ms | 29.3 ms | 32.8 ms | too_costly ×200 |
| `trust model data learning neural network training language agent task NOT (… 158 wildcards …)` | 0 | later page | 29.0 ms | 30.4 ms | 28.9 ms | 30.5 ms | too_costly ×200 |

## The real corpus: index `fd13d8d27535`, 133,629 records

| Query | Matches | Page | Without counts: median | p95 | With counts: median | p95 | Groups, per round |
|---|---|---|---|---|---|---|---|
| `(trust OR reliance) AND calibrat* AND model*` | 45 | first page | 16.4 ms | 17.6 ms | 23.1 ms | 24.0 ms | 3 counted ×200 |
| `(trust OR reliance) AND calibrat* AND model*` | 45 | later page | 4.6 ms | 5.0 ms | 4.6 ms | 5.1 ms | 3 counted ×200 |
| `("large language model$" OR LLM*) AND (trust* OR calibrat*) AND (benchmark* OR evaluat*)` | 310 | first page | 31.8 ms | 36.2 ms | 75.2 ms | 84.4 ms | 3 counted ×200 |
| `("large language model$" OR LLM*) AND (trust* OR calibrat*) AND (benchmark* OR evaluat*)` | 310 | later page | 30.5 ms | 35.6 ms | 30.5 ms | 38.3 ms | 3 counted ×200 |
| `trust model NOT (model NEAR/10 model*)` | 143 | first page | 26.9 ms | 35.2 ms | 44.5 ms | 70.1 ms | 2 counted ×200 |
| `trust model NOT (model NEAR/10 model*)` | 143 | later page | 22.9 ms | 25.3 ms | 22.9 ms | 27.7 ms | 2 counted ×200 |
| `trust model data learning neural network training language agent task` | 0 | first page | 2.3 ms | 2.7 ms | 29.2 ms | 35.8 ms | 10 counted ×200 |
| `trust model data learning neural network training language agent task` | 0 | later page | 2.0 ms | 2.3 ms | 2.1 ms | 2.3 ms | 10 counted ×200 |

### Every Trust-Evals string (`tests/golden/test_trust_evals.py`, Scholar syntax), as the API serves it

| Query | Matches | Page | Without counts: median | p95 | With counts: median | p95 | Groups, per round |
|---|---|---|---|---|---|---|---|
| `main-1` | 68 | first page | 25.4 ms | 28.4 ms | 40.4 ms | 44.2 ms | 3 counted ×200 |
| `main-1` | 68 | later page | 14.0 ms | 15.1 ms | 14.0 ms | 15.2 ms | 3 counted ×200 |
| `main-2-pop` | 114 | first page | 59.5 ms | 62.1 ms | 178.9 ms | 190.1 ms | 3 counted ×200 |
| `main-2-pop` | 114 | later page | 59.0 ms | 64.1 ms | 59.2 ms | 62.3 ms | 3 counted ×200 |
| `main-3-sources` | 68 | first page | 25.7 ms | 26.8 ms | 40.5 ms | 42.2 ms | 3 counted ×200 |
| `main-3-sources` | 68 | later page | 14.5 ms | 15.7 ms | 14.6 ms | 15.7 ms | 3 counted ×200 |
| `main-4-sources` | 30 | first page | 15.6 ms | 16.7 ms | 25.3 ms | 26.4 ms | 3 counted ×200 |
| `main-4-sources` | 30 | later page | 6.1 ms | 6.6 ms | 6.1 ms | 6.6 ms | 3 counted ×200 |
| `main-5-sources` | 22 | first page | 13.0 ms | 14.0 ms | 23.4 ms | 24.8 ms | 3 counted ×200 |
| `main-5-sources` | 22 | later page | 5.8 ms | 6.2 ms | 5.9 ms | 6.3 ms | 3 counted ×200 |
| `main-6-sources` | 33 | first page | 16.3 ms | 17.4 ms | 25.6 ms | 27.0 ms | 3 counted ×200 |
| `main-6-sources` | 33 | later page | 5.8 ms | 6.3 ms | 5.9 ms | 6.3 ms | 3 counted ×200 |
| `main-7-most-updated` | 33 | first page | 16.2 ms | 18.0 ms | 25.6 ms | 29.2 ms | 3 counted ×200 |
| `main-7-most-updated` | 33 | later page | 6.0 ms | 6.4 ms | 6.0 ms | 6.8 ms | 3 counted ×200 |
| `narrow` | 30 | first page | 15.3 ms | 17.5 ms | 25.0 ms | 28.1 ms | 3 counted ×200 |
| `narrow` | 30 | later page | 5.6 ms | 5.9 ms | 5.6 ms | 6.0 ms | 3 counted ×200 |
| `human-centered` | 4 | first page | 3.0 ms | 3.3 ms | 3.9 ms | 4.1 ms | 2 counted ×200 |
| `human-centered` | 4 | later page | 1.7 ms | 2.3 ms | 1.7 ms | 2.4 ms | 2 counted ×200 |
| `llm-as-judge` | 38 | first page | 13.0 ms | 14.1 ms | 16.1 ms | 17.4 ms | 3 counted ×200 |
| `llm-as-judge` | 38 | later page | 2.1 ms | 2.4 ms | 2.2 ms | 2.4 ms | 3 counted ×200 |
