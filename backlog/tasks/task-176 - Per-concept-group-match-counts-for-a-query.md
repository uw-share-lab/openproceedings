---
id: TASK-176
title: Per-concept-group match counts for a query
status: To Do
assignee: []
created_date: '2026-10-05 01:47'
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
- [ ] #1 For a query whose top level is an AND of groups, the API reports for each top-level text group the number of papers that group matches alone under the query's own filters (stated precisely in spec 04), with the group's code-point span
- [ ] #2 The counts are exact and reproducible for the same canonical query and index_version, and never change the result set, total, ranking or exclusion counts (00 guarantees 4, 5)
- [ ] #3 The extra work is bounded and admitted under the existing cost and rate limits (decision-010); a query over the bound gets the search result without group counts and says so
- [ ] #4 The builder shows each group's count after a search; a query that is not an AND of groups shows none
- [ ] #5 make openapi run and both contract files committed; specs 04 and 05 as built
<!-- AC:END -->
