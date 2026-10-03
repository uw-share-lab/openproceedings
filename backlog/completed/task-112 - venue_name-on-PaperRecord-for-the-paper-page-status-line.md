---
id: TASK-112
title: venue_name on PaperRecord for the paper page status line
status: Done
assignee: []
created_date: '2026-09-27 22:46'
updated_date: '2026-09-30 06:27'
labels:
  - api
  - frontend
milestone: m-3
dependencies: []
ordinal: 109000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-042: the paper page reads 'submitted to ICLR 2024' because the full conference name isn't in the API. Add venue_name (additive) from a per-venue-year table.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 venue_name in the record schema and API (additive),Paper page uses it,Table test per venue-year
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
venue_name is derived: a pydantic computed_field on PaperRecord over the existing per-venue-year table (vocab.CONFERENCES / venue_name(), the export venue string), excluded from records.jsonl (record.DERIVED), so no snapshot, index, index_version or RECORD_SCHEMA_VERSION change and every served index has it. Paper page status line reads paper.venue_name. Exports unchanged (RIS T2/BibTeX booktitle already carry the string; CSV/JSONL not asked for by spec 04). make openapi; table test per venue-year 2013-2026.
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
PaperRecord.venue_name: a computed field, vocab.venue_name(venue, year), the same venue string exports use as RIS T2 and BibTeX booktitle (per-venue-year table vocab.CONFERENCES). Never stored: record.DERIVED is excluded by snapshot.record_line and model_copy, so records.jsonl, snapshot hashes, index_version and RECORD_SCHEMA_VERSION are unchanged and existing indexes serve it with no rebuild; stored data naming it is refused (extra=forbid). Additive in /api/v1 (required, readOnly string on the PaperRecord schema; make openapi regenerated openapi.json and schema.ts). The paper page status line now reads 'submitted to International Conference on Learning Representations (ICLR 2024)', the copy deck's PA-5. Exports unchanged (CSV/JSONL keys and columns not changed; spec 04 doesn't ask). Tests: test_record.py pins all 42 venue-years 2013-2026 (decision-013 scope), derived-not-stored and refusal; contract tests for the schema and GET /papers; paper-view.test.tsx. Verified: make test (5829 passed, 2 skipped; vitest 2664 passed), make lint, make tooling green. Docs: spec 01, spec 04, record-schema and api-contract skills, design doc as-built.
<!-- SECTION:FINAL_SUMMARY:END -->
