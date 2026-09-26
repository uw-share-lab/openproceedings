---
id: TASK-031
title: Performance benchmarks against the spec 03 budgets
status: In Progress
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-09-26 22:51'
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

Review fixes (gate semantics confirmed: --benchmark-compare picks the saved base, fails on slowdowns only, the first PR only records, --benchmark-enable overrides the addopts; budgets really enforced when enabled). Shoulds: the report builds the index in a process of its own (as op index build does) and reports that process's peak memory, labelled as excluding its ~65 MB workers (the old figure included corpus generation and snapshot rendering); the report deletes its scratch corpus and index (unsealing the index first); the gate compares the minimum time (--benchmark-compare-fail=min:20%), the statistic least moved by runner noise. Nits: 40 rounds so the report's p95 isn't the max; the refused co* row counts distinct terms; cold match_ids clears the expansion cache too; the report itself says to regenerate on a quiet machine; the docstring says run from backend/; widest_stem uses compile.FIELDS; spec 07 says the search benchmark is warm and match_ids cold; checkout sets persist-credentials: false. Rejected: base/head on different Python minors (both steps use the same setup-uv and uv.lock pin, so they can't differ within one run). The report is regenerated at the current HEAD.

Regenerated report (quiet machine, c9fee21, 40 rounds): build 32.8 s, 99 MB, 401 MB peak in the build process; every Trust-Evals string within budget except main-2-pop cold (10.1 s search, 10.5 s match_ids + exclusions: the spec 03 exception); main-2-pop warm 63 ms. The earlier 147 ms warm reading (20 rounds, p95 = max, other load) didn't reproduce, so task-075 is archived with that reason and spec 03's measured line is corrected.

Verification (APPROVE; min:20% syntax and slowdown-only failure confirmed; RUSAGE_CHILDREN folds in the waited workers as a max, not a sum; 147 ms not reproduced even under load, main-2-pop warm p95 68-69 ms) nits fixed: the memory column says 'largest single process (the build; its workers are not summed)'; the report records git describe --always --dirty; a failed build prints its stderr; long lines rewrapped. Corrections to earlier notes: the gate is min:20%, not median; the 147 ms/task-075 item is superseded (archived, not reproduced). Report regenerated once more at the committed script.
<!-- SECTION:NOTES:END -->
