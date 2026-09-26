---
id: TASK-019
title: RIS importer for the Trust-Evals corpus (scholarmend mended.ris)
status: In Progress
assignee:
  - '@jeevan'
created_date: '2026-09-26 01:06'
updated_date: '2026-09-26 16:07'
labels:
  - ingest
milestone: m-2
dependencies:
  - TASK-018
ordinal: 18000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
M2 bootstrap source (spec 01 §Sources); claim-only status rule.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Imports both mended.ris files; abstracts never Scholar snippets (… rejected)
- [x] #2 status from claims only: venueid claim → its status; proceedings claim → accepted; none → unknown
- [x] #3 provenance.source = ris; per-file counts returned as an ImportReport for the snapshot manifest (manifest wiring is task-022 AC4)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented in backend/src/openproceedings/ingest/ris.py against scholarmend 0.1.3 (pinned). import_ris returns records plus an ImportReport per file; the manifest wiring (AC3's counts) and the op ingest ris entry point land with task-022 (its AC4). Real-corpus run, local only (2026-09-26): out-covidence (2025-26 search) 1391 read, 1377 imported, 12 out of scope, 2 no id (PMC-only ICML); out-covidence-2020-2024 443 read, 428 imported, 15 out of scope; 10 abstracts null (Scholar-only); no id shared by the two files; years fall inside each search's window.
<!-- SECTION:NOTES:END -->
