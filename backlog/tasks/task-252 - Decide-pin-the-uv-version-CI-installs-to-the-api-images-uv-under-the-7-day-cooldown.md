---
id: TASK-252
title: >-
  Decide: pin the uv version CI installs to the api image's uv, under the 7-day
  cooldown
status: To Do
assignee: []
created_date: '2026-10-16 22:50'
labels:
  - ci
  - decision
dependencies: []
ordinal: 165000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by the #154 review (2026-10-16): CI's setup-uv steps have no version, so CI installs the newest uv with no 7-day hold (decision-048's cooldown); on 2026-10-16 CI already ran uv 0.13.1 (2 days old) while deploy/api.Dockerfile pins 0.13.0. Pinning keeps CI, local and the image on one reviewed uv, at the cost of a hand bump alongside each image bump.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The owner decides; if yes, every setup-uv step pins the version deploy/api.Dockerfile pins, a make tooling check fails when they differ, and the Dependabot procedure and spec 08 say the two move together
<!-- AC:END -->
