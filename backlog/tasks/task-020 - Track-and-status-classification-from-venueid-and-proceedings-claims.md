---
id: TASK-020
title: Track and status classification from venueid and proceedings claims
status: In Progress
assignee:
  - '@jeevan'
created_date: '2026-09-26 01:06'
updated_date: '2026-09-26 15:57'
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
