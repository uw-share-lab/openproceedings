---
id: TASK-210
title: >-
  Say submission-time abstract in the API, every export and the UI, not only in
  provenance
status: In Progress
assignee: []
created_date: '2026-10-07 17:07'
updated_date: '2026-10-07 17:07'
labels:
  - api
  - export
  - frontend
milestone: m-4
dependencies: []
ordinal: 147000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-207 took ICML 1997 and 1998 abstracts from the official submission pages. Today the API, the exports (RIS, CSV, BibTeX, JSONL), the results list and the paper page label them only as ICML conference site <capture URL>; the note that they are submission-time abstracts, not necessarily the published paper's, is only in the claim evidence (provenance) and the coverage report. A reviewer who screens or cites from an export or the results list can't tell. Owner-approved 2026-10-07 (the follow-up proposed in TASK-207's notes).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The API response models (paper and search result) carry the submission-time note as a field, from one backend definition; make openapi regenerates openapi.json and frontend/src/api/schema.ts
- [ ] #2 RIS, CSV, BibTeX and JSONL exports carry the note in the field the ris-format and bibtex-format skills choose; goldens and fixtures regenerated
- [ ] #3 The results list and the paper page show the note next to the abstract in ux-writing words; unit, accessibility and visual tests cover it
- [ ] #4 Spec 04, spec 05 and the export docs describe the note
<!-- AC:END -->
