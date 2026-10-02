---
id: TASK-159
title: >-
  Link ICLR 2017 workshop-listing copies to their conference twins (within-crawl
  duplicates)
status: To Do
assignee: []
created_date: '2026-10-02 00:41'
labels:
  - ingest
  - dedup
milestone: m-4
dependencies: []
references:
  - backend/src/openproceedings/ingest/dedup.py
  - backend/src/openproceedings/ingest/sources/openreview_v1.py
  - docs/results/2026-10-01-iclr-2017-workshop-copies.md
  - .claude/skills/dedup-rules/SKILL.md
  - .claude/skills/openreview-venueids/SKILL.md
priority: low
ordinal: 134000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Source: a TASK-152 (PR #63) deferral (`docs/results/2026-10-01-iclr-2017-workshop-copies.md` §Duplicates within the ICLR 2017 crawl). ICLR 2017's workshop listing (`ICLR.cc/2017/workshop/-/submission`, 161 notes on the 2026-09-29 crawl) holds resubmissions of conference papers as separate OpenReview notes with their own forum ids, so they are separate records from their conference twins: the 18 whose `content.venue` is "Submitted to ICLR 2017" (each shares its title with a conference-listing note, and each one's `_bibtex` url names that twin's forum, e.g. `rkB_5hEKe` -> `ryh_8f9lg`) and 34 of the 35 "ICLR 2017 Invite to Workshop" notes, whose titles match a conference note but whose `_bibtex` names no twin (0 of 34). With the default filters off, a query counts each such paper twice under "identified"; the defaults remove both copies, since none is accepted. This predates TASK-152, which changed no merge. Linking the pairs is new dedup work: the two notes are different submissions with different tracks and outcomes (workshop/`unknown` vs main/`rejected`), so the dedup-rules never-merge rules and decision-005 govern whether this is a merge or only a link between two records.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A decision record (or an addendum to decision-005) says whether a workshop copy and its conference twin merge or stay two records linked to each other, and how the link is shown and exported; it cites the dedup-rules track rule and never-merge rules
- [ ] #2 The pairs are found by evidence that names the twin (the `_bibtex` forum id for the 18) and, if the decision allows it, by exact normalized title within ICLR 2017 for the 34; a test over recorded fixtures covers a `_bibtex` pair, a title-only pair, and a workshop note with no twin that stays unlinked
- [ ] #3 No two records with different forum ids are merged unless the decision says so, and merges.csv / conflicts.csv record every pair the rule links or refuses (dedup-rules audit formats)
- [ ] #4 A real-data before/after snapshot (`op snapshot diff`) shows only the ICLR 2017 pairs change, with the counts in the notes, and a default-filters-off query that matches some pairs shows how "identified" changes
- [ ] #5 spec 01, the record-schema and dedup-rules skills and the openreview-venueids 2013/2017 row describe the rule as built
<!-- AC:END -->
