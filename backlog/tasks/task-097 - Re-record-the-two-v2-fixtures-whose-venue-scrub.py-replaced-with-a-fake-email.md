---
id: TASK-097
title: Re-record the two v2 fixtures whose venue scrub.py replaced with a fake email
status: To Do
assignee: []
created_date: '2026-09-27 21:11'
labels:
  - ingest
  - testing
milestone: m-4
dependencies: []
ordinal: 94000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
scrub.py treated the @ in venue strings such as 'Tiny Papers @ ICLR 2023' as an email address (fixed in TASK-095). The v2 fixtures for Tiny Papers 2024 and the Mexico City workshop still carry the fake-email venue. Re-record them with the fixed scrub.py once OPENREVIEW_USERNAME/PASSWORD are in .env.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Both fixtures re-recorded with their real venue strings,Classifier table tests read the re-recorded venues
<!-- AC:END -->
