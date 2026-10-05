---
id: TASK-176
title: Per-concept-group match counts for a query
status: Done
assignee: []
created_date: '2026-10-05 01:47'
updated_date: '2026-10-05 08:38'
labels:
  - api
  - frontend
  - ux
milestone: m-3
dependencies: []
references:
  - docs/specs/04-backend-api.md
  - docs/specs/05-frontend.md
ordinal: 120000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
When a Boolean query of several AND-ed concept groups returns few papers, the reviewer cannot see which group is doing the cutting. On 2026-10-04 the Trust-Evals string kept 51 of 1,805 review papers, and it took a script to learn that the trust group alone removed 89% of them while the venue group removed none. Showing how many papers each top-level group matches on its own tells the reviewer which group to widen, with exact counts and no semantic layer.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 For a query whose top level is an AND of groups, the API reports for each top-level text group the number of papers that group matches alone under the query's own filters (stated precisely in spec 04), with the group's code-point span
- [x] #2 The counts are exact and reproducible for the same canonical query and index_version, and never change the result set, total, ranking or exclusion counts (00 guarantees 4, 5)
- [x] #3 The extra work is bounded and admitted under the existing cost and rate limits (decision-010); a query over the bound gets the search result without group counts and says so
- [x] #4 The builder shows each group's count after a search; a query that is not an AND of groups shows none
- [x] #5 make openapi run and both contract files committed; specs 04 and 05 as built
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. query/groups.py: split the effective tree's top-level conjuncts into groups (positive, text-searching) and what is kept for each (filters, defaults, NOT clauses); a group alone = the query with every other group removed.
2. TantivyEngine.count: |match_ids| from the facet combos (memoised per base), held to ReferenceEngine.
3. search.run(groups=limit): counts on a second worker with the request's read-only scope; GroupCounts on Search.
4. API: SearchResponse.groups {counts[{span,total}], groups_total, limit, not_counted}; ApiConfig.max_counted_groups (10), op serve --max-counted-groups; access-line fields.
5. Builder: group-counts.ts; a count per group and the total line, only while the draft is the searched query.
6. Specs 03/04/05/08, copy deck BD-12, design doc, skills, CLAUDE.md; make openapi.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Design: an additive, always-sent field on GET /search (no parameter, no second endpoint). Each counted group has two counts under the query's top-level filters (defaults included) and NOT clauses: total (the group alone: the query with every other group removed) and total_without (the query with that group removed; owner decision 2026-10-05). No position verification of its own (decision-010's cap, ceiling and charge cover every clause counted). Worst case per request: 2 x max_counted_groups (default 10) facet-style collections memoised in TantivyEngine.faceted, each non-filter conjunct compiled once and nothing stored in the compiled memo, one job on the worker pool, at most 2 s of waiting. The counts never cost the search its answer: a failure or a late worker gives not_counted count_failed / timed_out with the rest of the response whole.
Rejected: an opt-in parameter (two shapes of one response; the UI would always send it); a separate endpoint (a second parse, admission and verified-clause charge, and counts that could come from another index_version than total).
Real corpus (index 05a0541717f6, Scholar mode, the 2026-10-04 string with source:NeurIPS/ICLR/ICML and year:2020..2026): total 67; alone 6,343 (LLM), 529 (trust), 9,303 (benchmark); without 139, 2,337, 181.
Review round 1 (c3c01a74): Must (failure/timeout isolation), Shoulds (compiled-memo cost, property assertions, concurrency test) and Nits (spec sentences, 'same as group N', live status) fixed.
Needs a decision record (id to be assigned by the main session). Not done: an e2e/axe case for the builder with counts (ports 3000/8000 in use), and no learnings entry (INDEX.md would conflict across parallel branches).
<!-- SECTION:NOTES:END -->

## Comments

<!-- COMMENTS:BEGIN -->
created: 2026-10-05 04:41
---
Review round 2 (cost Must): TantivyEngine.counts compiles each conjunct once per request and stores nothing in the compiled memo (the 158-wildcard kept-clause shape: 2 entries / 19,106 units with or without counts, was 12 / 114,356); residual collection cost bounded by ApiConfig.max_counted_terms (default 5,000 terms read, N*G + 2*N*K), over which not_counted is too_costly.
---

created: 2026-10-05 05:00
---
Review round 2 (final): the pre-flight bound also covers verified ids (max_counted_ids, default 300,000); both bounds and the group limit are in /meta limits; counting runs on its own two workers and a timed-out job stops before its next collection; a worker's own TimeoutError is count_failed; 'same as group N' follows the server's ast.
---
<!-- COMMENTS:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
/search always sends groups: for each top-level text conjunct of the canonical tree, total (that group alone under the query's filters and NOTs) and total_without (the query with that group removed), with groups_total, limit and an open not_counted enum (fewer_than_two_groups, too_many_groups, too_costly, count_failed, timed_out, busy). Counted by TantivyEngine.counts on its own 2-worker pool, each conjunct compiled once per request, nothing stored in the compiled memo; bounded before any counting by max_counted_groups 10, max_counted_terms 5,000 and max_counted_ids 300,000 (in /meta); a 50 ms grace for a queued job and a 2 s bound for a running one; a failure or timeout never fails the search. Oracle-checked by property. The builder shows both numbers per group. decision-034. Three review rounds: 2 Musts (failure isolation, uncharged cost) and 5 Shoulds, fixed. e2e in TASK-182.
<!-- SECTION:FINAL_SUMMARY:END -->
