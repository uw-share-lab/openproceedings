---
id: TASK-152
title: >-
  ICLR 2017 workshop-listing notes marked Submitted to ICLR 2017 count as
  main/rejected
status: To Do
assignee:
  - '@jeevanp03'
created_date: '2026-09-30 20:05'
updated_date: '2026-09-30 20:10'
labels:
  - ingest
milestone: m-4
dependencies: []
references:
  - backend/src/openproceedings/ingest/classify.py
  - backend/src/openproceedings/ingest/ris.py
  - backend/src/openproceedings/ingest/sources/openreview_v1.py
  - .claude/skills/openreview-venueids/SKILL.md
priority: low
ordinal: 128000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Source: a TASK-142 (PR #47) review nit, rejected there (PR #47 body, Review, Nits). ICLR 2017 is the one year whose v1 venueid carries no track (`ICLR.cc/2017/conference`, lower case, which 2017 also puts on workshop invitations), so track comes from `content.venue` (`classify._V1_VENUE`; the v1 crawler by its `_NOT_A_TRACK` rule, the RIS importer via `classify.V1_TRACK_FROM_VENUE`, TASK-142). 18 notes from the workshop listing (`ICLR.cc/2017/workshop/-/submission`) carry `content.venue` "Submitted to ICLR 2017", which both paths map to `main`/`rejected`. So the ICLR 2017 main/rejected cell of the coverage breakdown is 18 too high. The count comes from the v1 crawler: no current RIS record is from 2017, but the importer would read such a record the same way. The result set under the default filters is unaffected, and so is `excluded.total`: the `status:accepted` default drops these notes whatever their track. Reclassifying them would move any that a query matches from the `status.rejected` exclusion bucket to `track.workshop` (spec 03 §Exclusion accounting: track first, then status), so the itemized PRISMA breakdown can shift by up to 18. The question is whether a 2017 note's track should come from the listing it was fetched from rather than from its `venue` string, and what its status then is. TASK-055 (the classification audit) is the check that would otherwise surface this.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A decision, recorded in the openreview-venueids skill (the `ICLR.cc/2017/conference`, `ICLR.cc/2013/conference` row) with its reason: either classify these notes by the listing they come from (workshop track, with the status that follows), or keep `main`/`rejected` and document the 18 as a known over-count
- [ ] #2 If the classification changes, the v1 crawler and the RIS importer give the same track and status for the same note (a test over a recorded fixture of one such note through each path), and a snapshot built after the change reports ICLR 2017 main/rejected 18 lower and the 18 in the chosen workshop cell (`op snapshot diff` before/after pasted in the notes)
- [ ] #3 For a query that matches some of the 18, a before/after run on the same inputs shows the result set and `excluded.total` unchanged, and any change to the per-filter breakdown is at most 18 and only from `status.rejected` to `track.workshop`
<!-- AC:END -->
