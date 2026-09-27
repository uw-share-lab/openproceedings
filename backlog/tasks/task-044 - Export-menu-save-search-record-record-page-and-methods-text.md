---
id: TASK-044
title: 'Export menu, save search record, record page and methods text'
status: To Do
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-09-27 20:27'
labels:
  - frontend
milestone: m-3
dependencies:
  - TASK-042
  - TASK-037
  - TASK-036
ordinal: 43000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Spec 05 §Components 7–8 and /record/[id].
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Methods text matches spec 05 verbatim, full index_version
- [ ] #2 mismatch shows the blocking 'do not cite' state with no methods text or export
- [ ] #3 Exports from the record page are pinned to its index
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Design (TASK-033, 2026-09-27): docs/design/2026-09-27-export-records-and-paper.md §Export menu E1-E4, §Save S1-S3, §Record R1-R6, §Methods text rules; copy deck §4-6. Export: GET /export?format&q&mode&index_version=<shown>; read headers first and abort if X-Index-Version or X-Total differ from the shown search (E3); status warning (E2) when filters.status admits non-accepted values, listing facets.status counts (never summed) - Covidence hides status from screeners (docs/results/2026-09-27-covidence-check.md); 'Importing into Covidence' disclosure EX-E7. Save: confirm dialog (public, permanent), then POST /records, then GET /records/{id} for status + methods text; STORE_FULL disables saving for the session. Record page: all values recorded (never the replay's) except the status block; drifted names each changed input and +a/-r with the paged diff; withheld/refused show no counts; mismatch renders no methods text and no export; exports disabled with reason when replay.index_version != record.index_version. API gaps for the API owner (main session to file): (1) identified_total and unclassified_total so the UI doesn't add total+excluded.total or the two unknown buckets (fallback: one unit-tested pure function); (2) default and limit clauses as text in the record (today only derivable via /parse(canonical) while query_version matches); (3) a way to read a record without a replay (?replay=false) for 429/API_BUSY.

Pre-pass fixes that land in TASK-044: compare the POST /records 201 index_version with the shown one and warn (SV-8, M3); drifted records itemise replay.excluded vs recorded when excluded_match is false (M4); track warning in the export menu (S2); same-index X-Total mismatch is a bug message, not 'index changed' (S3). BLOCKING API prerequisite for AC#1 (pre-pass S1): identified_total and unclassified_total (additive) - to be filed by the main session for the API owner. Also proposed: optional RecordRequest.index_version pin (409 like /export) and GET /records/{id}?replay=false (S4).
<!-- SECTION:NOTES:END -->
