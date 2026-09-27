---
id: TASK-020
title: Track and status classification from venueid and proceedings claims
status: Done
assignee:
  - '@jeevan'
created_date: '2026-09-26 01:06'
updated_date: '2026-09-26 18:34'
labels:
  - ingest
milestone: m-2
dependencies:
  - TASK-018
ordinal: 19000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Spec 01 §Track taxonomy (track-taxonomy, openreview-venueids skills).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Table test over every known venueid form incl. workshop satellite paths
- [x] #2 Never defaults to main; unparseable → unknown and logged
- [x] #3 Seeded with every distinct venueid form in the Trust-Evals 90 hand-verified OpenReview venueids (verification/openreview-venues.json; forms only, no forum ids or titles in this public repo)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Review (2026-09-26): track paths are now exact tuples per organisation (only the skill's rows reach a default-filter track; unseen aliases dropped); an unmapped status-like suffix is unknown, never accepted; a bare suffix, an invitation path (-) or a year outside 2013-2099 doesn't parse; workshop matched in any case. Note: AC #3 was reworded in 5f43f3f from venuescout's 92 workshop calls to the Trust-Evals 90 hand-verified venueids (forms only), because the venuescout calls are private data that can't be committed; the 90 venueids' forms are the seeded rows.

Verification round (2026-09-26): accepted only for a table path or a workshop (other paths take a mapped suffix's status, else unknown); status words any case, \w*_ prefix; the segment after Workshop is the name; unseen proceedings tokens unknown (Creative_AI_Track explicit other); rows for every organisation-ownership and year-bound mutant; skills updated.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Track/status classifier (ingest/classify.py): venueids parsed exactly against per-organisation track tuples; workshop wins; unmapped statuses and unknown forms never become accepted; proceedings tokens mapped explicitly. Verified: parametrised table tests including every reviewer form, two review rounds with mutation passes, and a read-only check of the Trust-Evals corpus forms (all classify as expected).
<!-- SECTION:FINAL_SUMMARY:END -->
