# What group counts add to a search (2026-10-10)

Regenerate with `uv run python -m tests.bench.group_counts_report --index <a copy of an index>` (from
`backend/`, on a quiet machine: other load inflates the timings); never edit by hand. TASK-176; cited by spec
04 §SearchResponse (`groups`, Cost) and spec 07 §E. Spec 03's 100 ms p95 budget covers a cold first page with
its counts (decision-039, TASK-197). A run is cited only when its 1-minute load (below) is under 5 at the start
and the end.

- Machine: Apple M1 Pro, macOS-15.6.1-arm64-arm-64bit, 8 CPUs; load average 2.7 / 4.0 / 4.8 at the
  start and 3.3 / 3.5 / 4.3 at the end (1, 5, 15 min); Python 3.12.15, tantivy
  0.26.2; commit `776feecd`.
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
| `(trust OR reliance) AND calibrat* AND model*` | 88 | first page | 9.4 ms | 9.9 ms | 33.6 ms | 50.0 ms | 3 counted ×200 |
| `(trust OR reliance) AND calibrat* AND model*` | 88 | later page | 6.5 ms | 7.0 ms | 11.1 ms | 11.9 ms | 3 counted ×200 |
| `trust model NOT (model NEAR/10 model*)` | 30 | first page | 6.1 ms | 6.7 ms | 13.4 ms | 15.2 ms | 2 counted ×200 |
| `trust model NOT (model NEAR/10 model*)` | 30 | later page | 1.3 ms | 1.4 ms | 3.6 ms | 3.9 ms | 2 counted ×200 |
| `agent ai benchmark calibration language bias dataset human trust model` | 0 | first page | 1.4 ms | 1.7 ms | 46.9 ms | 62.9 ms | 10 counted ×200 |
| `agent ai benchmark calibration language bias dataset human trust model` | 0 | later page | 0.6 ms | 0.8 ms | 7.8 ms | 9.0 ms | 10 counted ×200 |
| `trust model data learning neural network training language agent task NOT (… 158 wildcards …)` | 0 | first page | 29.2 ms | 31.5 ms | 29.3 ms | 32.6 ms | too_costly ×200 |
| `trust model data learning neural network training language agent task NOT (… 158 wildcards …)` | 0 | later page | 27.9 ms | 29.7 ms | 27.8 ms | 30.1 ms | too_costly ×200 |

## The real corpus: index `9977ed00669f`, 173,253 records

| Query | Matches | Page | Without counts: median | p95 | With counts: median | p95 | Groups, per round |
|---|---|---|---|---|---|---|---|
| `(trust OR reliance) AND calibrat* AND model*` | 60 | first page | 18.8 ms | 19.4 ms | 33.3 ms | 50.2 ms | 3 counted ×200 |
| `(trust OR reliance) AND calibrat* AND model*` | 60 | later page | 8.8 ms | 9.3 ms | 8.8 ms | 9.3 ms | 3 counted ×200 |
| `("large language model$" OR LLM*) AND (trust* OR calibrat*) AND (benchmark* OR evaluat*)` | 399 | first page | 33.8 ms | 34.9 ms | 59.7 ms | 61.2 ms | 3 counted ×200 |
| `("large language model$" OR LLM*) AND (trust* OR calibrat*) AND (benchmark* OR evaluat*)` | 399 | later page | 31.4 ms | 32.6 ms | 31.5 ms | 32.6 ms | 3 counted ×200 |
| `trust model NOT (model NEAR/10 model*)` | 232 | first page | 27.3 ms | 29.7 ms | 53.9 ms | 56.2 ms | 2 counted ×200 |
| `trust model NOT (model NEAR/10 model*)` | 232 | later page | 25.5 ms | 26.6 ms | 25.6 ms | 26.9 ms | 2 counted ×200 |
| `trust model data learning neural network training language agent task` | 0 | first page | 3.2 ms | 3.5 ms | 55.9 ms | 73.3 ms | 10 counted ×200 |
| `trust model data learning neural network training language agent task` | 0 | later page | 2.6 ms | 2.9 ms | 3.6 ms | 3.9 ms | 10 counted ×200 |

### Every Trust-Evals string (`tests/golden/test_trust_evals.py`, Scholar syntax), as the API serves it

| Query | Matches | Page | Without counts: median | p95 | With counts: median | p95 | Groups, per round |
|---|---|---|---|---|---|---|---|
| `main-1` | 103 | first page | 24.7 ms | 25.7 ms | 44.6 ms | 46.7 ms | 3 counted ×200 |
| `main-1` | 103 | later page | 23.9 ms | 25.2 ms | 24.0 ms | 25.2 ms | 3 counted ×200 |
| `main-2-pop` | 169 | first page | 63.9 ms | 66.0 ms | 84.9 ms | 90.3 ms | 3 counted ×200 |
| `main-2-pop` | 169 | later page | 63.7 ms | 65.5 ms | 63.8 ms | 66.7 ms | 3 counted ×200 |
| `main-3-sources` | 68 | first page | 26.6 ms | 27.8 ms | 46.6 ms | 48.1 ms | 3 counted ×200 |
| `main-3-sources` | 68 | later page | 15.7 ms | 16.8 ms | 15.8 ms | 16.9 ms | 3 counted ×200 |
| `main-4-sources` | 30 | first page | 16.3 ms | 17.3 ms | 30.5 ms | 31.4 ms | 3 counted ×200 |
| `main-4-sources` | 30 | later page | 6.9 ms | 7.5 ms | 6.9 ms | 7.5 ms | 3 counted ×200 |
| `main-5-sources` | 22 | first page | 13.6 ms | 14.5 ms | 27.0 ms | 28.1 ms | 3 counted ×200 |
| `main-5-sources` | 22 | later page | 6.6 ms | 7.2 ms | 6.7 ms | 7.3 ms | 3 counted ×200 |
| `main-6-sources` | 33 | first page | 16.8 ms | 17.6 ms | 30.6 ms | 31.5 ms | 3 counted ×200 |
| `main-6-sources` | 33 | later page | 6.6 ms | 7.1 ms | 6.6 ms | 7.1 ms | 3 counted ×200 |
| `main-7-most-updated` | 33 | first page | 16.8 ms | 17.7 ms | 30.5 ms | 31.7 ms | 3 counted ×200 |
| `main-7-most-updated` | 33 | later page | 6.5 ms | 7.0 ms | 6.6 ms | 7.0 ms | 3 counted ×200 |
| `narrow` | 46 | first page | 19.5 ms | 20.4 ms | 32.4 ms | 33.4 ms | 3 counted ×200 |
| `narrow` | 46 | later page | 6.4 ms | 6.9 ms | 6.5 ms | 6.9 ms | 3 counted ×200 |
| `human-centered` | 10 | first page | 5.7 ms | 6.2 ms | 7.9 ms | 8.2 ms | 2 counted ×200 |
| `human-centered` | 10 | later page | 2.2 ms | 2.4 ms | 2.2 ms | 2.5 ms | 2 counted ×200 |
| `llm-as-judge` | 47 | first page | 15.7 ms | 16.5 ms | 22.5 ms | 23.4 ms | 3 counted ×200 |
| `llm-as-judge` | 47 | later page | 2.5 ms | 2.8 ms | 2.6 ms | 2.9 ms | 3 counted ×200 |
