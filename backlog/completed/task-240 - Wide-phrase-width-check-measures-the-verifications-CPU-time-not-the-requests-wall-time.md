---
id: TASK-240
title: >-
  Wide-phrase width check measures the verification's CPU time, not the
  request's wall time
status: Done
assignee: []
created_date: '2026-10-12 13:36'
updated_date: '2026-10-12 13:56'
labels:
  - tests
  - ci
dependencies: []
ordinal: 167000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
PR #141 (TASK-239) moved every CPU-time check in backend/tests onto tests/timing.py, but left one growth check on the wall clock: width_is_free in backend/tests/contract/test_verification_scale.py, which times requests TestClient serves on another thread, where this thread's thread_time sees nothing. Wall-clock checks flake on shared CI runners (nightly 37943547380 timed a 17 ms parse at 1.9 s). The check guards M3a round 4: a 300-item wildcard phrase rebuilt its allowed-token sets per item per candidate (84 s at 80k against 3.8 s for 2 items). The owner asked for it to be fixed.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The check measures CPU time through tests/timing.py, with the cyclic collector paused, and no wall-clock bound remains in it
- [x] #2 A deliberately width-superlinear verification (the pre-round-4 set rebuild) still fails it
- [x] #3 The check and its neighbours pass repeatedly, idle and under CPU load; the pr-workflow local runs, make lint and make tooling pass
- [x] #4 The test docstring, timing.py's docstring, testing-standards and the learning describe the design as built
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Measure the server-side verification CPU the access line already logs (verify_cpu_ms) through timing.growth with a measure parameter; pause the collector with a shared collector_paused.
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
width_is_free now compares the widest wildcard phrase with the narrowest by the verifying thread's CPU time, read from each request's access line (verify_cpu_ms), through timing.growth's paired, alternated median (new measure parameter) with the cyclic collector paused (new collector_paused, which cpu uses). Bound: under 2x (width-free measures ~0.95 idle, ~0.88 under ten CPU burners). The pre-round-4 per-candidate set rebuild, patched in locally, fails at 5.7-6.25. No product change: the field already existed. Process CPU time was rejected because facet and group-count workers can outlive a response. Tests: make test (9099 passed, 3 skipped; frontend 4953), the check and neighbours 3x idle and 3x under load at -n 4, the opt-in 80k variant once, make lint, make tooling. Docs: test docstring, timing.py docstring, test_timing.py, testing-standards, learning addendum.
<!-- SECTION:FINAL_SUMMARY:END -->
