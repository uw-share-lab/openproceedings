---
id: TASK-227
title: >-
  A drifted search record explains each removed paper: moved to another track,
  or no longer in the index
status: Done
assignee: []
created_date: '2026-10-10 16:33'
updated_date: '2026-10-10 19:13'
labels:
  - api
  - frontend
  - records
dependencies: []
ordinal: 157000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
From the fix/aaai-aies-tracks review gate (review-methodologist S1, 2026-10-10). When a saved record replays as drifted, its removed list gives only id and title, so a reviewer cannot tell that a paper moved to student_abstract, iaai or demo (decision-050) rather than being deleted. Add each removed entry's current track (or 'not in the index') and a per-cause tally to the records diff route and the record page. Owner: milestone C (feat/new-venues-c), which is changing the records API and record page now; a precondition of the v0.3.0 release.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The records diff route gives each removed id's current track or 'not in the index', and a per-cause tally
- [x] #2 The record page shows the same, in plain language
- [x] #3 Contract and frontend tests pin both; done before v0.3.0 is tagged
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. records.removals/removal_cause/track_clauses: each removed id's track (TantivyEngine.tracks, a stored-field read) and cause against the effective query's top-level track clauses. 2. DiffEntry gains track and cause; RecordDiff gains removed_causes; access line gets the counts. 3. record-diff.tsx shows the cause per removed paper and the tally (RC-14a). 4. Contract, unit, fixture and Vitest tests.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Additive: DiffEntry gains track (its track on the replaying index, also on added entries) and cause (null on an added entry) rather than a RemovedEntry subtype, because the additive-contract checker counts a changed items $ref as breaking. removal cause is an OPEN enum. Eligibility = passing the effective query's top-level track: clauses (the default included), decided by tantivy_engine.passes (renamed from _passes). A status change on an admitted track reads still_eligible. Verified: full backend suite (8765 passed), npm test --workspace frontend (4932 passed), make lint, make tooling, make openapi clean, make e2e on 8100/3100 (67 passed).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
GET /records/{id}/diff now says why each removed paper is gone, judged on the replaying index: track_changed (with its current track), not_in_index, or still_eligible, plus removed_causes counted over the whole list; the record page's diff shows each cause in plain language and the tally line (copy RC-14a). ids_hash, replay status and existing fields are unchanged; the cause is a stored-field read, no index field. Tests: a contract test replaying on a second index where one paper moved to IAAI, one left and one no longer matches; unit tests for removal_cause and the tally; a real drift case in record-fixture.json and Vitest for the diff view. Verified with the full backend suite, the frontend suite, make lint and e2e on the alternate ports.
<!-- SECTION:FINAL_SUMMARY:END -->
