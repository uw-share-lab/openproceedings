---
id: TASK-210
title: >-
  Say submission-time abstract in the API, every export and the UI, not only in
  provenance
status: Done
assignee: []
created_date: '2026-10-07 17:07'
updated_date: '2026-10-07 19:27'
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
- [x] #3 The results list and the paper page show the note next to the abstract in ux-writing words; unit, accessibility and visual tests cover it
- [x] #4 Spec 04, spec 05 and the export docs describe the note
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
One definition (ingest/dedup.py SUBMISSION_NOTE, read through Attribution.as_submitted from the icml_site claim's evidence, which icml_sites._evidence writes with the AS_SUBMITTED constant, byte-identical) carried to the API (abstract_note on Hit and PaperResponse), RIS (an N1 after Abstract source), BibTeX (abstract_note field; note stays provenance), CSV (abstract_note column appended last), JSONL (abstract_note key only when present, like twins) and the UI (a muted line under the attribution in the results list and under the abstract on the paper page; copy RH-19/PA-11). No snapshot or index change.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
make openapi regenerated openapi.json and schema.ts; record-fixture.json regenerated. Tests: backend unit+contract green, vitest 4,865, make e2e 66 passed (darwin baselines submission-note-{light,dark}-darwin.png added). Linux baselines come from CI's e2e artifact (spec 05 §Testing: never on an arm64 Mac). Open question for the owner (2026-10-07, not decided by this branch; spec 04 describes what is built): JSONL carries abstract_note only on a record that has one (as twins does) rather than null on every record; and the exact wording of the note.

Linux baselines submission-note-{light,dark}-linux.png taken from CI e2e run 37673211616's playwright-report artifact (the test's actual screenshots, checked by eye), per spec 05 §Testing.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
One sentence, ingest/dedup.py SUBMISSION_NOTE ('Submission-time abstract: as the authors submitted it, which may differ from the published paper's.'), derived at snapshot load from the icml_site claim's evidence marker AS_SUBMITTED (byte-identical to what TASK-207 wrote, so no snapshot or index change), now reaches the API (abstract_note on search hits and GET /papers/{id}; null when withheld or missing), every export (RIS N1 after Abstract source; BibTeX abstract_note; CSV abstract_note column appended last; JSONL key only when present) and the UI (a muted line under the result's attribution and under the paper page's abstract; copy RH-19, PA-11). Contract regenerated (openapi.json, schema.ts), record fixture regenerated, contract/unit/vitest/e2e (a11y + visual, darwin and Linux baselines) cover it; prisma-reporting skill gains the screening gotcha. Owner question left open: JSONL key only when present vs null everywhere, and the wording.
<!-- SECTION:FINAL_SUMMARY:END -->
