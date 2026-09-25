---
id: TASK-002
title: Verify unconfirmed OpenReview and proceedings facts against live data (M4)
status: To Do
assignee: []
created_date: '2026-09-25 22:06'
labels:
  - ingest
dependencies: []
references:
  - .claude/skills/openreview-venueids/SKILL.md
ordinal: 2000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The ingestion skills mark these 'verify'. Confirm each with recorded fixtures before writing classifiers.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 venueid forms confirmed with a recorded example each: Desk_Rejected, bare /Submission, D&B 2024+ without Track/, 2021 D&B Round1/Round2, ICML and NeurIPS position tracks, Tiny Papers, Blogposts, Competition
- [ ] #2 PMLR volumes for ICML 2025+ and competition/workshop volumes added to the volume table with sources
- [ ] #3 Whether NeurIPS 2021 D&B has a separate proceedings host
- [ ] #4 OpenReview max page size and .env variable names confirmed
- [ ] #5 openreview-venueids, pmlr-proceedings and neurips-proceedings skills updated; the 'verify' markers removed
<!-- AC:END -->
