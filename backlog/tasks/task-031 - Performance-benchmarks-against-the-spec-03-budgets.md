---
id: TASK-031
title: Performance benchmarks against the spec 03 budgets
status: In Progress
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-09-26 22:25'
labels:
  - engine
  - ops
milestone: m-2
dependencies:
  - TASK-030
ordinal: 30000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
pytest-benchmark suite; bench workflow compares against main (performance-profiler).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 p95 search < 100 ms, match_ids with exclusions < 300 ms, 200-term expansion < 50 ms on the fixture
- [x] #2 bench workflow fails on a >20% regression
- [x] #3 Position-verified queries (stopword NEAR and wildcard phrases, e.g. the NEAR/5 the, "the*" NEAR/5 model) measured on the ~80k corpus against spec 03's exception for verified clauses, with results in the benchmark report
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented: backend/tests/bench/test_bench.py (pytest-benchmark 5.3, dev dependency) on the synthetic 5k index: a 50-hit search and match_ids with exclusion accounting (cold verified cache) for every Trust-Evals string in Scholar mode, the widest expansion at or under the cap (117 terms) and one past it (co*, refused), each asserting its spec 03 budget on the p95 of 30 rounds; all pass (slowest: main-2-pop match_ids 72 ms). Benchmarks are disabled in ordinary runs (pyproject addopts --benchmark-disable; they then run once as tests); .github/workflows/bench.yml runs them enabled on the PR's base and head on one runner and fails a median regression over 20% (--benchmark-compare-fail=median:20%), recording only when the base has no suite. backend/tests/bench/report_80k.py generates the same synthetic corpus at 80k with 120-250-word abstracts and writes docs/results/2026-09-26-bench.md (quiet machine): build 35 s, 99 MB; all strings within budget except main-2-pop (wildcard phrases, position-verified): 10.3 s cold (spec 03's exception) and 147 ms warm, over the search budget -> task-075 (M4). Verified stopword cases 2.2-3.3 s cold. Expansion 0.3 ms (124 terms), refusal 1.1 ms. An earlier run under load showed main-1 at 126 ms; the quiet rerun gives 35-40 ms, so reports must be taken on a quiet machine (the report says so). docs: spec 03 measured line, spec 07 §E as built, spec 08 CI table (bench row), performance-profiler agent commands.
<!-- SECTION:NOTES:END -->
