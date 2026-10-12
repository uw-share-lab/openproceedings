---
id: TASK-239
title: 'Linear-time checks measure the algorithm, not the garbage collector'
status: Done
assignee: []
created_date: '2026-10-12 03:35'
updated_date: '2026-10-12 03:45'
labels:
  - tests
  - ci
dependencies: []
ordinal: 166000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
CI test runs 38176036366 (the merge queue for PR #138) and 38197206724 (PR #140) failed `test_a_hostile_page_is_parsed_in_linear_time[icml2007_paper]` at growth ratios 8.09 and 8.24 against the < 8 bound of `backend/tests/timing.py`, introduced by PR #137 the same day to stop timing flakes. The parser is linear (36, 69, 131, 262, 527 ms for 57-807 KB locally). A flaky gate on unrelated PRs blocks the merge queue; the owner asked for it to be fixed outright, without weakening the checks against quadratic or backtracking regressions.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Root cause verified with evidence (CI pairs, a local reproduction) before the fix
- [x] #2 The linear-time checks no longer charge a call for costs sized by the test process rather than the input
- [x] #3 tests/unit/test_timing.py still shows a quadratic fails, plus one for what changed
- [x] #4 Every linear-time check in backend/tests uses tests/timing.py
- [x] #5 timing.py module docstring, the test docstring, testing-standards and the learning describe the design as built
- [x] #6 Affected tests pass repeatedly, idle and under CPU load; make test, make lint and make tooling pass
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Verify the root cause from the CI pairs and a local reproduction (GC counts around growth in a -n 4 suite run; memory-bandwidth burners for the cache hypothesis). 2. Pause the cyclic collector inside tests/timing.py cpu; keep allocation and freeing timed. 3. Tests: quadratic allocation fails; no collection inside a timed call; collector restored. 4. Move test_latex_scan and test_highlight_speed onto growth(calls=8). 5. Docs as built: timing.py docstring, test docstring, testing-standards, learning addendum.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Root cause: full garbage collections. CI pairs (38176036366, 38197206724): small side 0.06-0.09 s except pair 0 at 0.33-0.47 s (a discrete full collection), large 0.49-0.76 s vs 0.26 s locally. Local -n 4 suite with gc.get_stats logged around growth: icml2007_paper ratio 5.45, large 366 ms, 8 gen-2 collections in the measurement; with the collector paused 3.84, 246 ms. Cache hypothesis refuted locally: 7 memory-bandwidth burners left the ratio 3.5-4.0 (collector paused). Negative controls (local, not committed): former _find scans in tokenize fail the LaTeX check at 15.9; a page-rescanning step in the ICML parse fails icml2007_paper at 10.5 (stride 64) and 13.4 (stride 16). Validation: linear-time subset (58 tests) 3x idle and 5x under 8 yes burners, all pass; make test 9097 passed + 4953 frontend; make lint, make tooling pass. timing.py has no mutants configured.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
tests/timing.py cpu now pauses the cyclic garbage collector while it times a call: a full collection costs the xdist worker's whole heap and fired mostly on the large side, which failed icml2007_paper at 8.09 and 8.24 in CI. Allocation and freeing stay timed; test_timing.py shows a quadratic in work and one in allocation still fail, and that no collection runs inside a timed call. test_latex_scan and test_highlight_speed now use growth(calls=8). Verified by a local reproduction (5.45 to 3.84), repeated runs idle and under load, make test, make lint, make tooling.
<!-- SECTION:FINAL_SUMMARY:END -->
