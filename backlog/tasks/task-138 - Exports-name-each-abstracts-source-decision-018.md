---
id: TASK-138
title: Exports name each abstract's source (decision-018)
status: In Progress
assignee:
  - '@jeevanp03'
created_date: '2026-09-30 02:40'
updated_date: '2026-09-30 04:20'
labels:
  - export
milestone: m-6
dependencies:
  - TASK-134
ordinal: 121000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-018 requires attribution wherever an abstract is shown or exported. TASK-134's review found no export names the abstract's source: RIS N1 and BibTeX note carry only the openproceedings line; RIS UR and BibTeX url give links but nothing says which source the abstract came from. Decide the mapping under the api-contract and export-format rules (an extra RIS N1 line or a CSV/JSONL column may be additive).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The export mapping for the abstract's source is decided and recorded (additive vs breaking per api-contract)
- [x] #2 RIS, BibTeX, CSV and JSONL exports carry it, with round-trip tests against scholarmend's RIS parser and refaudit's BibTeX parser
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Depends on TASK-134, whose abstract_source helper exports can reuse (TASK-134's AC#3 export note lands here). Blocks TASK-069: decision-018 attributes every record to its source and PMLR's CC BY 4.0 requires attribution when the text is handed out, which an export does. Spec 04 §Exports.

Mapping (spec 04 §Exports 'Abstract source in every format'; ris-format, bibtex-format and api-contract skills): RIS one more N1 'Abstract source: <site> <url>' after the status sentence, before the provenance line (still last); BibTeX a new field abstract_source = {<site> <url>} after abstract (note unchanged); CSV three columns appended after searched_at: abstract_source, abstract_origin, abstract_url; JSONL abstract_source {source, origin, url} or null (the /search hit's object). Site words = results list's ORIGIN_NAMES (+ ' (via RIS import)' for ris claims; 'an imported RIS file' when no known site). Nothing for a record with no abstract or none a claim holds. Classified additive: no existing line/field/column changes value or position; N1 already repeated (Covidence imported the rejected fixture record's two N1s; shows no N1 to screeners); api-contract §Versioning rules now state the export-additive rule. Source: RecordFile.attributions (TASK-134), passed as a required sources= to export.entries/write; a record missing from it is EngineInternalError. Pinned index_version/record exports load their own snapshot via new IndexState.pinned_records (lazy, open slot, LRU, refusal remembered); snapshot unverifiable -> 409 API_INDEX_VERSION_UNAVAILABLE before the first byte. op export verifies the snapshot (snapshot_records). Covidence fixture bytes unchanged (its records carry no claims), no re-import needed. Tests: backend/tests/contract/test_export_attribution.py (17: every format vs snapshot and vs /search abstract_source, scholarmend RIS + refaudit BibTeX read-back, PMLR link, op export bytes = API, pinned index, record on its own index, snapshot gone 409, pinned records cached, refusal memory, CLI without snapshot fails); backend/tests/unit/test_export.py (byte-exact per-format golden for a PMLR record, unchanged bytes without a source, CSV column positions, credit() wording, N1 order, BibTeX escaping, missing-id error, ORIGIN_NAMES == hit-item.tsx). Verification: make lint 0, make tooling 0; make test twice: all export/api tests green, one unrelated Hypothesis timing flake each run (test_openreview_v1_authors too_slow health check; test_reference_200 DeadlineExceeded under load), both pass on rerun.
<!-- SECTION:NOTES:END -->
