---
id: TASK-210
title: >-
  Say submission-time abstract in the API, every export and the UI, not only in
  provenance
status: In Progress
assignee: []
created_date: '2026-10-07 17:07'
updated_date: '2026-10-07 19:01'
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
- [x] #1 The API response models (paper and search result) carry the submission-time note as a field, from one backend definition; make openapi regenerates openapi.json and frontend/src/api/schema.ts
- [x] #2 RIS, CSV, BibTeX and JSONL exports carry the note in the field the ris-format and bibtex-format skills choose; goldens and fixtures regenerated
- [ ] #3 The results list and the paper page show the note next to the abstract in ux-writing words; unit, accessibility and visual tests cover it
- [x] #4 Spec 04, spec 05 and the export docs describe the note
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
One definition (ingest/dedup.py SUBMISSION_NOTE, read through Attribution.as_submitted from the icml_site claim's evidence, which icml_sites._evidence writes with the AS_SUBMITTED constant, byte-identical) carried to the API (abstract_note on Hit and PaperResponse), RIS (an N1 after Abstract source), BibTeX (abstract_note field; note stays provenance), CSV (abstract_note column appended last), JSONL (abstract_note key only when present, like twins) and the UI (a muted line under the attribution in the results list and under the abstract on the paper page; copy RH-19/PA-11). No snapshot or index change.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
make openapi regenerated openapi.json and schema.ts; record-fixture.json regenerated. Tests: backend unit+contract green, vitest 4,865, make e2e 66 passed (darwin baselines submission-note-{light,dark}-darwin.png added). Linux baselines come from CI's e2e artifact (spec 05 §Testing: never on an arm64 Mac). Open question for the owner (2026-10-07, not decided by this branch; spec 04 describes what is built): JSONL carries abstract_note only on a record that has one (as twins does) rather than null on every record; and the exact wording of the note.
<!-- SECTION:NOTES:END -->
