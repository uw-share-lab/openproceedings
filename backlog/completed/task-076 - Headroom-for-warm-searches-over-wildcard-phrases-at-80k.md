---
id: TASK-076
title: Headroom for warm searches over wildcard phrases at 80k
status: Done
assignee: []
created_date: '2026-09-26 23:03'
updated_date: '2026-10-02 02:50'
labels:
  - engine
  - performance
milestone: m-4
dependencies:
  - TASK-031
ordinal: 74000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
task-031: on a quiet M-series Mac with the synthetic 80k corpus, main-2-pop (wildcard phrases such as model$, position-verified, all clauses cached) searches warm at median 61 ms, p95 95 ms, p99 148 ms over 200 runs, against spec 03's 100 ms p95 for a 50-hit search. Within budget, but slower hardware would cross it. The cached id sets still feed a term_set_query beside the full candidate query, whose scoring over ~4.4k matches dominates. Options: cache the compiled Tantivy query per (canonical, index_version), or score verified candidates from the cached ids only. (Replaces the archived task-075 finding, whose 147 ms came from a noisy 20-round run.)
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Differential suite green; scores unchanged (determinism test)
- [x] #2 main-2-pop warm search p95 < 50 ms and p99 < 100 ms over 200 warm rounds in report_80k.py on a quiet machine
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Before M2's gate: the report (200 warm rounds) gave main-2-pop warm p95 68.7 ms; a separate 200-run probe (not in docs/results) gave p95 95 ms, p99 148 ms.

M2 gate: TantivyEngine.compile is now memoised per tree (bounded), so a search's pages and facets don't rebuild the Boolean; the balanced combine trees cost ~5x Python compile time for wide wildcards (perf review).

Current: docs/results/2026-09-27-bench.md, regenerated at f0de68b (clean tree, quiet machine), gives main-2-pop warm p95 27.5 ms; cold search 10.1 s and match_ids + exclusions 10.5 s (the spec 03 exception). AC#2's p95 < 50 ms is met; its p99 < 100 ms isn't measured yet (add a p99 column to report_80k.py, or a probe) before closing.

TASK-076 (2026-10-02): warm cost was Tantivy re-resolving each verified clause's id term set per search (~0.5 us an id). Compiler.exact names the shorter list: the verified ids (as before), or the candidates that failed as a MUST_NOT term set (or the candidate query alone when none failed); same ids and same float scores (tests/unit/engine/test_verified_exclusion.py: crafted forms + every engine_asts tree on the 5k corpus with and without the form). report_80k now has a warm p99 column; docs/results/2026-10-02-bench.md (01e8632, quiet: load 10.1 -> 3.5, no test run): main-2-pop warm p95 27.8 ms, p99 31.7 ms. Alternating old/new (tests/bench/warm_verified.py, load ~4): real corpus main-2-pop p95 46.8 -> 27.3 ms; synthetic unchanged (its big clause, AI agent$ with 20,752 ids vs 53,620 failures, keeps its ids). Results: docs/results/2026-10-02-wildcard-phrases.md.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
A position-verified clause now compiles to its candidate query with whichever id list is shorter: the verified ids (a constant-0 term set, as before) or the candidates that failed (excluded), since Tantivy resolves an id set on every search. Same ids and same float scores, proven by a property over every differential-suite tree on the 5k corpus with and without the form, plus crafted cases and hand mutants. report_80k gained a warm p99 column; on a quiet machine main-2-pop warm is p95 27.8 ms, p99 31.7 ms (synthetic 80k), and on the real M4 corpus its warm search fell from p95 46.8 to 27.3 ms.
<!-- SECTION:FINAL_SUMMARY:END -->
