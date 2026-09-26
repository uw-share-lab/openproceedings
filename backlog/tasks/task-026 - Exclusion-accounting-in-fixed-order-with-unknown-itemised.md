---
id: TASK-026
title: Exclusion accounting in fixed order with unknown itemised
status: In Progress
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-09-26 20:35'
labels:
  - engine
milestone: m-2
dependencies:
  - TASK-024
  - TASK-014
ordinal: 25000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Spec 03 §Exclusion accounting (default-filters, prisma-reporting skills).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Buckets assigned track first then status; sum equals excluded.total
- [x] #2 unknown itemised separately; only default filters count
- [x] #3 Golden cases for overlap (rejected workshop paper counts once under track.workshop)
- [x] #4 Counts come from ParseResult.identification_ast and defaults (never by re-parsing identification_query, which can be "" or all-negative); golden cases for both
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented engine/exclusions.py: excluded(engine, parsed) -> Excluded(total, track, status) over the Engine protocol only (two disjunctive facet counts + one match_ids), so both engines compute it identically. Track buckets = track facet of identification ∧ track-default (counts every identified record); status buckets = status facet of the effective query (identified records that passed the track default); unknown always its own key, last. A sum mismatch is API_INTERNAL. Counts come from identification_ast/defaults; a garbled identification_query changes nothing (tested for the "" and all-negative cases). Tests: both engines vs a brute-force count on the 200-record fixture (10 queries: typed default, nested filter, own track set, no defaults, year limit, phrase/wildcard), every bucket exercised, the rejected-workshop overlap, refusal of a query with errors. Hand mutants 9/10 killed; the survivor was equivalent, and a dead nonzero filter it exposed was removed.
<!-- SECTION:NOTES:END -->
