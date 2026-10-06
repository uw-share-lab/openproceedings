---
id: TASK-197
title: >-
  A cold first page of main-2-pop with group counts runs its first group three
  times and misses the 100 ms p95 budget
status: Done
assignee: []
created_date: '2026-10-05 17:21'
updated_date: '2026-10-06 03:25'
labels:
  - perf
  - search
milestone: m-3
dependencies: []
references:
  - docs/results/2026-10-05-bench-group-counts.md
ordinal: 141000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
docs/results/2026-10-05-bench-group-counts.md (index fd13d8d27535, 200 rounds, 1-minute load 3.9 then 3.3): the Trust-Evals string main-2-pop takes p95 190.1 ms on a cold first page with its group counts, against 62.1 ms without them and 62.3 ms on a later page; spec 03 carries it as an exception "as measured" under decision-039. Found while closing TASK-196 on 2026-10-05.

Cause, measured on a scratch copy of the index: the first group (nine alternatives, seven of them `$` phrases) costs about 35 ms a run and is a conjunct of three of the six trees TantivyEngine.counts collects (the group alone, and the query without each other group), so each of those trees runs it again; the nested terms aggregation itself costs no more than Tantivy's count collector on these trees (sums agreed with the count on all 58 Trust-Evals trees). Running the group once and reusing its matches as an `ord` term set (Query.term_set_query) took the three trees from about 113 ms to about 57 ms (materialising 39 ms; g1 AND g2 36.4 to 7.4 ms; g1 AND g3 41.8 to 10.7 ms), which alone leaves the cold page near 120 ms: the page and its facets run the same group too, so the fix likely shares one materialisation across the page, the facets and the counts, within the memo budgets and without changing any count (guarantee 4; test_group_counts.py holds counts to match_ids and ReferenceEngine).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A cold first page of every Trust-Evals string with its group counts at the default bounds is under the 100 ms p95 budget on the current index, measured with group_counts_report.py at a 1-minute load under 5 at the start and the end
- [x] #2 Every group count is unchanged: test_group_counts.py passes, and its counts still equal match_ids and ReferenceEngine on the shapes it covers
- [x] #3 Spec 03's "Exception, as measured (decision-039, TASK-197)" bullet is removed and spec 04's Cost figures are regenerated from that run
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Compiled records each top-level conjunct's query (and a NOT's child's); search.run hands the request's compile to the counting worker, so TantivyEngine.counts compiles nothing again (the recompile, with exact()'s count and members collections per verified clause, was about a fifth of the counting time).
2. When a conjunct holding a position-verified clause is in two or more counted bases, counts collects each distinct conjunct once as a bitmap of ords (order_by_field ord: no scoring), ANDs them per tree (a NOT conjunct subtracts its child's), and reads each base's (venue, year, track, status) combos from per-value bitmaps built once per engine; stored in faceted as before. Otherwise the per-tree aggregation as before.
3. Tests: bitmap combos equal the aggregation's on generated bases; counts with the request's compile equal counts without it and ReferenceEngine; each shared conjunct collected once; check stops between collections; concurrency with the masks rebuilt under it; memo budgets unchanged.
4. Measure by ratio (cold first page with vs without counts, before vs after, alternated) with the load recorded; the quiet re-measure and report stay with the main session.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Measure names (2026-10-05, gate round 1 PERF nit): 'about 35 ms a run' is the group's count alone (Tantivy's count collector on its query, best of 5); 'materialising 39 ms' is a search returning every hit's address plus reading their ord fast-field values and building the term set, best of 3. Both on the scratch copy of fd13d8d27535 at a 1-minute load near 4.

Implemented on v011/perf (2026-10-05), awaiting the main session's quiet re-measure (AC #1) and the spec 03/04 figures (AC #3):
- Compiled.conjuncts: each top-level conjunct's query (a NOT's child's too), recorded as the compile builds them; search.run passes the request's compile to the counting worker, so counts compiles nothing again (that recompile ran exact()'s count and members collections per verified clause).
- TantivyEngine.counts: when a conjunct holding a verified clause is in two or more bases, and the call has no more distinct conjuncts than distinct bases, each distinct non-filter conjunct is collected once as a bitmap (order_by_field ord: no scoring), a base is the AND of its conjuncts' bitmaps (a NOT's child's subtracted), and its combos are read from per-value bitmaps (_masks, built once per engine, ~0.5 MB at 133k docs, uncharged like the ord table). Combos stored in faceted as before. Otherwise the per-tree aggregation as before.
- Ratios on the scratch copy of fd13d8d27535 (cold first page = faceted cleared; plain / before / after alternated in one process, 'before' = the old path patched in): main-2-pop median after/plain 1.22-1.39 vs before/plain 3.03-3.23; p95 at a load of 30.5 → 25.0: plain 72.4, before 221.9, after 86.2 ms (40 rounds). The wildcard-phrase query: p95 81.1 → 51.7; 'trust model NOT (model NEAR/10 model*)': 46.1 → 38.4. The other nine Trust-Evals strings unchanged (no verified clause: old path). Not quiet-machine figures: the load was 25-130 throughout.

2026-10-06 quiet re-measure (group_counts_report.py, load 3.4 → 4.6, commit 66613463 = dev after #112): main-2-pop cold first page with counts p95 85.4 ms (median 73.8; 65.6 ms without counts), from 190.1 ms; every Trust-Evals string within 100 ms (next highest main-1 46.1 ms). Counts unchanged (test_group_counts.py holds them to match_ids and ReferenceEngine). Spec 03's exception removed and spec 04's Cost figures regenerated from docs/results/2026-10-06-bench-group-counts.md.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Counting reuses the request's compile and collects a conjunct shared by several counted trees once into an ord bitmap (PR #112), with the copies it keeps charged to the compiled memo. A cold first page of main-2-pop with its counts went from p95 190.1 ms to 85.4 ms at a quiet load; every Trust-Evals string is within the 100 ms budget, so decision-039's exception is closed.
<!-- SECTION:FINAL_SUMMARY:END -->
