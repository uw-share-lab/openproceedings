---
id: TASK-088
title: >-
  Headroom for the /search first page at 80k: non-ASCII tokenizer fast path,
  real-corpus re-measure
status: Done
assignee: []
created_date: '2026-09-27 11:38'
updated_date: '2026-10-02 01:56'
labels:
  - engine
  - performance
milestone: m-4
dependencies:
  - TASK-086
priority: medium
ordinal: 86000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
After task-086 a /search first page (search.run(limit=50, facets=True, highlight=True)) on the synthetic 80k index cost 75-117 ms p95 CPU (main-1 117 ms, main-3-sources 109 ms). Breakdown of main-1 (median CPU): page collection 34 ms, the base's facet-combo aggregation 37 ms, highlighting 50 hits 33 ms (almost all query/normalize.py _tokenize_each_char: the synthetic generator's text is ~50% non-ASCII and misses the ASCII fast path, real abstracts ~23%), Python facet/exclusion counting 3 ms, display 1 ms. Two collections of the text query are the floor of an exact design (the page needs the effective query's own scores; reusing the base collection's scores is not provably bit-identical, because compile.combine groups the conjuncts differently once filters join), and facets need the base.

Done in the M3a review gate round 2 (option 1): search.run compiles the effective tree in the request's thread (cold verified clauses take their verification slot there), then runs the facet aggregation on a worker thread overlapping the page collection, display and highlighting (Tantivy releases the GIL). Output identical to the sequential path (tests/unit/test_search_overlap.py; tests/contract/test_search_overlap.py). Wall p95 over 200 runs at 80k: 57-85 ms for every non-empty Trust-Evals string (main-1 84.5 ms), CPU per request unchanged 74-109 ms (docs/results/2026-09-27-search-overlap.md). The budget is met in wall time; CPU per request, which bounds throughput, is not reduced.

What remains is headroom, for M4: (2) a tokenizer fast path for non-ASCII Latin text (query/ owners; needs the frozen-copy parity test and no TOKENIZER_VERSION change), which cuts highlighting CPU; (3) re-measure on the real corpus once M4 lands, where highlighting is cheaper.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The /search first page is under 100 ms wall p95 at 80k for every Trust-Evals string, measured the way report_80k's /search columns measure it (wall time, at least 100 rounds), or spec 03 records the exception with numbers
- [x] #2 No ID set, score, facet or exclusion count changes (differential, golden, test_facets_equal, test_search_overlap)
- [x] #3 A fast path in query/normalize.py's loop for the texts that leave the whole-text ASCII path (non-ASCII characters or LaTeX), pinned to a frozen copy of the loop (no TOKENIZER_VERSION bump), measured in CPU per request
- [x] #4 report_80k's /search columns re-measured on the real M4 corpus with no other test run going (old and new alternated, load recorded), and spec 03's Measured updated
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
PR #6 bench (advisory): test_match_ids_with_exclusions_on_a_broad_query min +31% vs dev on the 5k fixture (~1.46 → 1.91 ms), because exclusion accounting now uses the one combos collection (TASK-086). Option: let exclusion-only callers (op search without facets) skip the combos aggregation.

TASK-088 (2026-10-01): the loop's fast paths, all exact, no TOKENIZER_VERSION bump: a text with no \ or $ skips the LaTeX mask; a stretch of KEEP ASCII characters with no mark after it is taken word by word; _fold_char folds a raw character once per process when its fold is the same after a base of each _folds_marks class (_BASES; bounded table _FOLDED). Pinned, tokens and Tail, to a frozen copy of the loop at 05eff53 (tests/unit/tokenize_before_088.py) and still to task-073's tokenize_before. Measured in docs/results/2026-10-01-tokenizer-fast-path.md (old and new alternated round by round, 200 rounds, load 15-31, no other test run): tokenizer CPU 57-75% of before on the real corpus, 60% on the synthetic; /search first page median CPU 0.6-8 ms lower on the real corpus, 11-13 ms lower on the synthetic 80k. Real M4 corpus (05a0541717f6, 95,877 records): every Trust-Evals string's first page within budget, wall p95 3-75 ms (main-2-pop 74.8 ms; its cost is its wildcard phrases, task-076). Not done here: the PR #6 bench note's option (exclusion-only callers skip the combos aggregation).

Review gate round 1 (2026-10-01): the fold table now checks its bound before probing (a full table cost five folds per miss); the next-non-ASCII search is reused so stretch searches stay linear (task-070's linear-time test caught it); the timing harness is committed (tests/bench/alternate.py); every table re-measured at 952401a at load 4-8 with no other test run. AC #3 and #4 reworded as built: the fast path is for every text off the whole-text path, not Latin only (two thirds of real ones are LaTeX), and 'quiet machine' is 'no other test run, load recorded' (shared machine; old and new alternated).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Made query/normalize.py's per-character loop faster with three exact shortcuts (no LaTeX mask without a backslash or dollar; ASCII stretches word by word; base-independent folds cached in a bounded table), proven token- and Tail-identical against a frozen copy of the loop (tests/unit/tokenize_before_088.py), the task-073 oracle, the whole-string definition (OP_EXHAUSTIVE run too) and a by-hand check of the cache over every code point. Re-measured with tests/bench/alternate.py (old and new alternated, load 4-8): /search first-page median CPU 0.6-8.1 ms lower on the real M4 corpus and 11.5-12.7 ms lower on the synthetic 80k; on the real corpus every Trust-Evals string's first page is within budget (wall p95 2.9-73.4 ms). Spec 03, the token-contract skill and docs/results/2026-10-01-tokenizer-fast-path.md updated.
<!-- SECTION:FINAL_SUMMARY:END -->
