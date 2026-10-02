---
id: TASK-166
title: >-
  Let exclusion-only callers skip the facet-combination aggregation (TASK-088
  deferral)
status: In Progress
assignee: []
created_date: '2026-10-02 09:27'
updated_date: '2026-10-02 18:39'
labels:
  - engine
  - performance
  - deferred
dependencies: []
references:
  - backend/src/openproceedings/engine/exclusions.py
  - backend/tests/bench/test_bench.py
priority: low
ordinal: 136000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Source: TASK-088, PR #6 bench note, deferred. Exclusion accounting reads its buckets from the same facet-combination aggregation as the sidebar facets, so a caller that needs only the exclusion counts (an export, a record save, `op search` without facets) still pays for every facet combination. PR #6's bench measured tests/bench/test_bench.py::test_match_ids_with_exclusions_on_a_broad_query at about 1.46 ms before and 1.91 ms after (+31%, 5k fixture). The full /search aggregation is about 37 ms median CPU at 80k (TASK-088 notes). Add a path that computes only the exclusion buckets for those callers. Not needed for the 100 ms budget, which TASK-088 met in wall time; this is CPU headroom.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 test_match_ids_with_exclusions_on_a_broad_query is back to about its pre-PR #6 time (about 1.46 ms on the 5k fixture), with the before/after numbers in docs/results/
- [x] #2 Exclusion counts are identical to the facet path for every Trust-Evals string (test_facets_equal or a new equality test); no ID set or count changes
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
TantivyEngine.facets/combos take over (the aggregated fields; only their top-level filters set aside, the others stay in the collected query). search.run without facets (op search, record save and replay) passes exclusions.ORDER (track, status): 45 combos instead of up to 1,080. Measured in docs/results/2026-10-02-exclusions-and-verified-forms.md with tests/bench/exclusions_alternate.py (old and new alternated, load 30-155 recorded): the bench's broad query on 5k went from 1.7 to 0.7 ms warm p50, below the pre-PR #6 1.46 ms; 1-2 ms saved warm on the synthetic 80k, nothing measurable on the real corpus (at most 32 combos). test_bench's exclusion bench and report_80k's exclusion column now run the search-without-facets path; report_80k's cold rounds also clear the facet memo, as its comment says they clear every cache.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Exclusion accounting for a search without facets now aggregates only the two default fields (TantivyEngine.facets over=ORDER), the same counts (test_facets_equal: generated trees, every Trust-Evals string, ReferenceEngine; test_search_overlap). The 5k bench's broad query is 0.7 ms warm p50 (was 1.7 ms; pre-PR #6 1.46 ms). Results: docs/results/2026-10-02-exclusions-and-verified-forms.md.
<!-- SECTION:FINAL_SUMMARY:END -->
