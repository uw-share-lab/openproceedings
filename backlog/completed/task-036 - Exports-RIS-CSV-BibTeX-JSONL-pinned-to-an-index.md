---
id: TASK-036
title: 'Exports: RIS, CSV, BibTeX, JSONL pinned to an index'
status: Done
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-09-27 17:50'
labels:
  - api
milestone: m-3
dependencies:
  - TASK-035
  - TASK-004
ordinal: 35000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Spec 04 §Exports (ris-format, bibtex-format skills).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 RIS imports into Covidence (one manual fixture) and round-trips through scholarmend.parse.parse_ris
- [x] #2 BibTeX parses with refaudit; note carries provenance
- [x] #3 X-Total and X-Index-Version headers; record_id or index_version pins the source index
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. export.py: split write() into header()/entries() + utc_date() so op export and the API share bytes. 2. search.expanded(): located wildcard refusal shared by /search and /export. 3. IndexState.pinned(v): other index_versions validated like the configured index. 4. api/export.py router: parse/pin/expand/collect before the first byte, sync generator StreamingResponse, count check. 5. Contract tests + spec 04 as-built + CLAUDE.md layout.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Validate BibTeX with refaudit.bibtex.parse_string and RIS with scholarmend.parse.parse_ris, both from PyPI, pinned as root dev dependencies (refaudit 0.4.9 at 2026-09-25).

Built GET /api/v1/export (api/export.py): q, format, mode, index_version. Body == op export bytes (contract test per format x 4 queries). X-Total/X-Index-Version/Content-Type/Content-Disposition. Pinned index_version via IndexState.pinned (index_path rules; alias symlink and 'current' refused; 409 API_INDEX_VERSION_UNAVAILABLE). Round-trips over the API: RIS via scholarmend.parse_ris, BibTeX via refaudit.parse_string (note = provenance), CSV, JSONL, all == match_ids in id order. Hot-swap and mid-stream-abort tests use the real route. Tests: backend/tests/contract/test_export.py.
AC#1 NOT ticked: its automated half (scholarmend round-trip over the API) is done, but 'imports into Covidence (one manual fixture)' is TASK-004 AC#1's pending human import (docs/results/2026-09-27-covidence-check.md); the API body is byte-identical to op export, so that check covers it once done.
AC#3 NOT ticked: X-Total/X-Index-Version and index_version pinning are done; the record_id half is TASK-037's. Hook: api/export.py::pinned_engine(request, served, index_version) — add a record_id param to the route, resolve it to the record's index_version there (422 both given / malformed, 404 API_RECORD_NOT_FOUND, 409 API_RECORD_MISMATCH for a mismatch replay), before the stream starts; extend test_the_openapi_document_describes_the_export's param set.

2026-09-27 review round (branch fix-036-pinned): record_id wired (either q [+mode, index_version] or record_id alone; record_id + q/mode/index_version = 422; api.records.require_citable gives 404 / 409 API_RECORD_MISMATCH before any byte). X-Tokenizer-Version and X-Query-Version headers added and exposed to CORS. Pinned loaders unified: IndexState.pinned(version) -> Pinned(engine, reason ok|absent|unloadable|tampered); api/pinned.py removed. Review Shoulds S1-S5 and nits fixed with tests (test_export.py, test_pinned.py, test_serve.py). AC#1 still pending the human Covidence import (TASK-004 AC#1), so the task stays In Progress.

2026-09-27 M3a docs gate: AC#1's parser is scholarmend.parse.parse_ris (the pinned PyPI package), not venuetriage's; AC#1 stays unticked until the human Covidence import (docs/results/2026-09-27-covidence-check.md). AC#3 was ticked after the record_id review round (fix-036-pinned), which wired /export?record_id=.

AC#1 done 2026-09-27 via the Covidence hand check (the API's RIS body is byte for byte op export's; fixture pinned).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
GET /api/v1/export streams RIS/CSV/BibTeX/JSONL byte-identical to op export, pinned by index_version or record_id (stored ids), refusals before the first byte, X-Total and version headers; RIS verified in Covidence 2026-09-27.
<!-- SECTION:FINAL_SUMMARY:END -->
