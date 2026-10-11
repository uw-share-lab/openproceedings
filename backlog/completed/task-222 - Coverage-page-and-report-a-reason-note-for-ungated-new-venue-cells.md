---
id: TASK-222
title: 'Coverage page and report: a reason note for ungated new-venue cells'
status: Done
assignee: []
created_date: '2026-10-10 05:14'
updated_date: '2026-10-10 19:55'
labels:
  - eval
  - frontend
  - new-venues
milestone: m-6
dependencies: []
ordinal: 155000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Raised by the milestone A review gate: an ungated cell such as IASEAI 2026 (57 archival of 92 accepted; 35 non-archival unpublished) shows no reason on /coverage or in op eval coverage. coverage-causes.toml takes failing cells only, so this needs a field for an ungated cell's note in the API (spec 04 §coverage) and copy on the page (copy deck CV rows).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Ungated cells can carry a cited note shown on /coverage and in the report
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Built: official_counts.UngatedNote, UNGATED_NOTES (IASEAI 2026; AAAI 2011 definition mismatch; AAAI 2016 list appears derived from the proceedings; AAAI 2022-2026 not found), check_notes at import (refuses a gated cell, an unknown venue/track, an empty note or citation). coverage-sources.md gains §Ungated cells with a note, kept equal by test_official_counts.py (the parser now picks each table by its header). GET /coverage tracks carry gate_note and gate_note_citation (additive; null for gated cells and cells without a note); the report adds '## Ungated cells with a note'; /coverage shows the note under the track's row (copy deck CV-9). Validation: full backend suite 8782 passed; npm test --workspace frontend 4935 passed; make lint clean; op eval coverage --check on index 99c2e7ea2a0a (snapshot 2026-10-10-21779e017036, the newest index; the newest snapshot 9efa49481112 has no index, same AAAI main counts) PASS 83 of 84 and the report lists the 8 notes.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Ungated cells can carry a cited note: official_counts.UNGATED_NOTES (checked at import, mirrored by coverage-sources.md §Ungated cells with a note), served as gate_note/gate_note_citation on GET /coverage, shown under the track's row on /coverage (CV-9) and listed in op eval coverage's report. Notes for IASEAI 2026 and AAAI 2011, 2016, 2022-2026 main. Verified by unit, contract and Vitest tests, and a real op eval coverage --check run that passes and lists the notes.
<!-- SECTION:FINAL_SUMMARY:END -->
