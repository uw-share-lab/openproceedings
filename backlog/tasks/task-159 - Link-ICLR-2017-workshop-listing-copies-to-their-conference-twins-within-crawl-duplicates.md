---
id: TASK-159
title: >-
  Link ICLR 2017 workshop-listing copies to their conference twins (within-crawl
  duplicates)
status: In Progress
assignee:
  - '@jeevanp03'
created_date: '2026-10-02 00:41'
updated_date: '2026-10-02 05:45'
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
Source: a TASK-152 (PR #63) deferral (`docs/results/2026-10-01-iclr-2017-workshop-copies.md` §Duplicates within the ICLR 2017 crawl). ICLR 2017's workshop listing (`ICLR.cc/2017/workshop/-/submission`, 161 notes on the 2026-09-29 crawl) holds resubmissions of conference papers as separate OpenReview notes with their own forum ids, so they are separate records from their conference twins. Two groups: the 18 whose `content.venue` is "Submitted to ICLR 2017" (each shares its title with a conference-listing note that is itself "Submitted to ICLR 2017", and each one's `_bibtex` url names that twin's forum, e.g. `rkB_5hEKe` -> `ryh_8f9lg`), and 34 of the 35 "ICLR 2017 Invite to Workshop" notes, whose titles match a conference note but whose `_bibtex` names no twin (0 of 34). The two groups differ: the 18 pair a workshop/`unknown` record (since TASK-152) with a main/`rejected` one, while the 34 pair two workshop/`unknown` records (the twins are the conference listing's "Invite to Workshop" notes; a read-only re-tally of the 2026-09-29 cache for this task, not in the results doc, so re-measure it). In both groups what keeps them apart is dedup-rules §Never merge: two different forum ids are different submissions, and dedup never decides that two OpenReview notes are one paper. With the default filters off, a query counts each such paper twice under "identified"; the defaults remove both copies, since none is accepted. This predates TASK-152, which changed no merge. The precedent for deciding two OpenReview notes are one paper is in the crawler, before dedup (`openreview_v1.collapse_duplicate_submissions`, TASK-125; `collapse_silent_twins`, TASK-132), not in dedup; decision-005 governs which source wins a merged field.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A decision record says whether a workshop copy and its conference twin are collapsed into one record (in the crawler, as TASK-125/TASK-132 do, or in dedup) or stay two records linked to each other, and how the link is shown and exported; it cites dedup-rules §Never merge, the track rule (for the 18) and decision-005, and may decide the 18 and the 34 differently
- [ ] #2 The pairs are found by evidence that names the twin (the `_bibtex` forum id for the 18) and, if the decision allows it, by exact normalized title within ICLR 2017 for the 34; a test over recorded fixtures covers a `_bibtex` pair, a title-only pair (linked or left unlinked, as the decision says), and a workshop note with no twin that stays unlinked
- [ ] #3 A real-data before/after snapshot (`op snapshot diff`) shows only ICLR 2017 pairs change, with the counts in the notes (including the 34 twins' venue strings, re-measured), and a default-filters-off query that matches some pairs shows "identified" before and after (unchanged if the decision is link-only)
- [ ] #4 spec 01, the record-schema and dedup-rules skills and the openreview-venueids 2013/2017 row describe the rule as built
- [ ] #5 No two records with different forum ids become one record (the owner chose link, not merge); every link is recorded on both records as a `twin` claim with its evidence and counted in the crawl report's `twins_linked`, and a copy left unlinked because several main-track submissions share its title (its `_bibtex` naming none) is counted in `twins_ambiguous`, so refusals are auditable from the manifest
<!-- AC:END -->
