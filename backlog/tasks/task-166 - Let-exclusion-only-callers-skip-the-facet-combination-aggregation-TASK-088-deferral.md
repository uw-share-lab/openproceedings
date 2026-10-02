---
id: TASK-166
title: >-
  Let exclusion-only callers skip the facet-combination aggregation (TASK-088
  deferral)
status: To Do
assignee: []
created_date: '2026-10-02 09:27'
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
- [ ] #1 test_match_ids_with_exclusions_on_a_broad_query is back to about its pre-PR #6 time (about 1.46 ms on the 5k fixture), with the before/after numbers in docs/results/
- [ ] #2 Exclusion counts are identical to the facet path for every Trust-Evals string (test_facets_equal or a new equality test); no ID set or count changes
<!-- AC:END -->
