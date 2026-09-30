---
id: TASK-138
title: Exports name each abstract's source (decision-018)
status: Done
assignee:
  - '@jeevanp03'
created_date: '2026-09-30 02:40'
updated_date: '2026-09-30 05:29'
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
Depends on TASK-134, whose abstract_source helper exports reuse (TASK-134's AC#3 export note lands here). Blocks TASK-069: decision-018 attributes every record to its source and PMLR's CC BY 4.0 requires attribution when the text is handed out, which an export does. Spec 04 §Exports.

Mapping (spec 04 §Exports 'Abstract source in every format'; ris-format, bibtex-format and api-contract skills; decision-021): RIS one more N1 'Abstract source: <site> <url>' after the status sentence, before the provenance line (still last); BibTeX a new field abstract_source = {<site> <url>} after abstract (note unchanged); CSV four columns appended after searched_at: abstract_source, abstract_origin, abstract_url, abstract_withheld; JSONL abstract_source {source, origin, url} or null (the /search hit's object) and abstract_withheld (bool). Site words = results list's ORIGIN_NAMES (+ ' (via RIS import)' for ris claims; 'an imported RIS file' when no known site). Nothing for a record with no abstract or none a claim holds. Classified additive (decision-021 rule 1): no existing line/field/column changes value or position; api-contract §Versioning rules state the export-additive rule.

Source: RecordFile.attributions (TASK-134), passed as a required sources= to export.entries/write; a record missing from it is EngineInternalError. Pinned index_version/record exports load their own snapshot via IndexState.pinned_records (lazy, open slot, LRU, refusal remembered until refusal_seconds or reload). A pinned index whose snapshot can't be verified is NOT refused (owner, 2026-09-30, decision-021, reversing a first-cut 409 that never shipped): the same records go out with every abstract withheld, X-Abstract-Source: unavailable (attributed otherwise), and each record says so (RIS N1 / BibTeX abstract_withheld = WITHHELD sentence; CSV/JSONL abstract_withheld true). op export verifies the snapshot (snapshot_records); without it, same withholding plus a stderr warning, exit 0. Covidence fixture bytes unchanged (its records carry no claims), no re-import needed.

Tests: backend/tests/contract/test_export_attribution.py (every format vs snapshot and vs /search abstract_source, scholarmend parse_ris + refaudit parse_string read-back, PMLR link, op export bytes = API, pinned index, record on its own index, snapshot gone -> withheld on the index_version and record paths with replay still reproduced, pinned records cached, refusal memory, CLI without snapshot withholds with a warning); backend/tests/unit/test_export.py (byte-exact per-format golden for a PMLR record, CSV column positions, credit() wording, N1 order, BibTeX escaping, missing-id error, ORIGIN_NAMES == hit-item.tsx).

Review gate (2026-09-30): the access line carries abstract_source (the X-Abstract-Source sent); the web app reads X-Abstract-Source and, on unavailable, still saves the file but shows copy EX-E8 in the Export menu and the record page's exports (announced too), since Covidence hides the file's withheld N1 from screeners; pinned_records' LRU and refusal expiry now tested (three-index store, clocked refusal_seconds); the CORS test derives the exposed set from every declared response header; odd source urls (@, unbalanced braces, non-ASCII, 5k chars, a line break) read back through both reference parsers.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Every export now names each abstract's source (decision-018): RIS an extra N1 'Abstract source: <site> <url>' before the provenance line, BibTeX an abstract_source field, CSV abstract_source/abstract_origin/abstract_url/abstract_withheld appended last, JSONL abstract_source ({source, origin, url} or null) and abstract_withheld. The attribution is the snapshot's RecordFile.attributions (what /search sends), for the served index and, via IndexState.pinned_records, for pinned index_version and search-record exports; op export verifies the snapshot too. Additions to an export format are additive under /api/v1 and a pinned export whose snapshot can't be verified withholds its abstracts, marked in the file and by X-Abstract-Source: unavailable (decision-021, owner 2026-09-30). Verified: RIS and BibTeX read back with scholarmend's parse_ris and refaudit's parse_string (test_export_attribution.py), byte-exact unit goldens (test_export.py); make test (5674 passed, 2 skipped; vitest 2659 passed), make lint 0, make tooling 0.

Review gate: withheld exports are also visible on the access line (abstract_source) and in the web app (copy EX-E8 in the Export menu and the record page).
<!-- SECTION:FINAL_SUMMARY:END -->
