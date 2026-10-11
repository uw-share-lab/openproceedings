---
id: TASK-203
title: >-
  Extend the corpus before 2013: NeurIPS from 1987, ICML from 1988 (decision-047
  supersedes decision-013's floor)
status: Done
assignee: []
created_date: '2026-10-07 03:15'
updated_date: '2026-10-07 05:44'
labels:
  - ingest
  - docs
milestone: m-4
dependencies: []
ordinal: 146000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The owner decided on 2026-10-06 to index the full history of NeurIPS and ICML. decision-013 kept every venue from 2013 (ICLR's first year) and said years before 2013 stay out until a spec change; this task records the new decision and makes the specs, coverage page, official counts, README and CLAUDE.md say what the corpus now holds, including that per-venue year coverage now differs (ICLR starts in 2013).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 decision-047 records the owner's decision, the sources per venue-year (NeurIPS proceedings 1987-2012; ICML from the pinned dblp snapshot release 1988-2012, abstracts from official ICML pages) and supersedes decision-013's pre-2013 exclusion
- [x] #2 Spec 00 open question 3, spec 01 (Sources year ranges, crawl window, the dblp and ICML-site source rows, the abstract-source rule), spec 02's year coverage line and spec 04/07 wherever they state year ranges are updated
- [x] #3 The coverage page and official counts cover the new venue-years, and say that ICLR has no pre-2013 years so cross-venue year counts differ before 2013
- [x] #4 README and CLAUDE.md mention the new range and the new source
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Write decision-047; update spec 00/01/02/04/07, coverage-sources.md and official counts, the coverage page (year spans, CV-7), README, CLAUDE.md and the skills.
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
decision-047 supersedes decision-013's 2013 floor (NeurIPS from 1987, ICML from 1988; decision-013 notes it). Spec 00 (scope, open question 3), 01 (sources, crawl window, dblp and ICML sites rows, abstract rule, PDF-code cleaning, CLI), 02, 04, 07 and 08, coverage-sources.md (26 NeurIPS rows; ICML before 2013 reported, not gated), README (intro, quickstart, M4 row), CLAUDE.md and the skills are current. The coverage page names each venue's indexed years and says the venues start in different years (CV-7, tested). New snapshot 2026-10-07-3292905d4c80, index f6754b2efa63: coverage gate PASS (71 of 72 gated cells within 1%, 1 accepted exception); the Trust-Evals query returns the same 101 ids as on fd13d8d27535 (docs/results/2026-10-07-pre-2013-snapshot.md).
<!-- SECTION:FINAL_SUMMARY:END -->
