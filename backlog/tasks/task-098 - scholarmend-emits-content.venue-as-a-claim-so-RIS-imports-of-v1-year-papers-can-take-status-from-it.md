---
id: TASK-098
title: >-
  scholarmend emits content.venue as a claim so RIS imports of v1-year papers
  can take status from it
status: To Do
assignee: []
created_date: '2026-09-27 21:11'
labels:
  - ingest
milestone: m-4
dependencies: []
ordinal: 95000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Since TASK-095 a v1 venueid is not status evidence, and the RIS importer has no other status source for a v1-year paper without a proceedings listing, so it imports as status:unknown. If scholarmend emitted OpenReview content.venue as a claim, classify_v1_venue could set the status. No current corpus record is affected (the audit found 0 v1-year records).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 scholarmend's RIS output carries content.venue for OpenReview papers,The importer passes it to classify_v1_venue and records the claim's provenance,Tests over the v1 fixtures
<!-- AC:END -->
