---
id: TASK-197
title: >-
  A cold first page of main-2-pop with group counts runs its first group three
  times and misses the 100 ms p95 budget
status: To Do
assignee: []
created_date: '2026-10-05 17:21'
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

Cause, measured on a scratch copy of the index: the first group (nine alternatives, six of them `$` phrases) costs about 35 ms a run and is a conjunct of three of the six trees TantivyEngine.counts collects (the group alone, and the query without each other group), so each of those trees runs it again; the nested terms aggregation itself costs no more than Tantivy's count collector on these trees (sums agreed with the count on all 58 Trust-Evals trees). Running the group once and reusing its matches as an `ord` term set (Query.term_set_query) took the three trees from about 113 ms to about 57 ms (materialising 39 ms; g1 AND g2 36.4 to 7.4 ms; g1 AND g3 41.8 to 10.7 ms), which alone leaves the cold page near 120 ms: the page and its facets run the same group too, so the fix likely shares one materialisation across the page, the facets and the counts, within the memo budgets and without changing any count (guarantee 4; test_group_counts.py holds counts to match_ids and ReferenceEngine).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A cold first page of every Trust-Evals string with its group counts at the default bounds is under the 100 ms p95 budget on the current index, measured with group_counts_report.py at a 1-minute load under 5 at the start and the end
- [ ] #2 Every group count is unchanged: test_group_counts.py passes, and its counts still equal match_ids and ReferenceEngine on the shapes it covers
- [ ] #3 Spec 03's "Exception, as measured (decision-039, TASK-197)" bullet is removed and spec 04's Cost figures are regenerated from that run
<!-- AC:END -->
