---
id: TASK-044
title: 'Export menu, save search record, record page and methods text'
status: In Progress
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-09-27 23:12'
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
- [x] #1 Methods text matches spec 05 verbatim, full index_version
- [x] #2 mismatch shows the blocking 'do not cite' state with no methods text or export
- [x] #3 Exports from the record page are pinned to its index
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Design (TASK-033, 2026-09-27): docs/design/2026-09-27-export-records-and-paper.md §Export menu E1-E4, §Save S1-S3, §Record R1-R6, §Methods text rules; copy deck §4-6. Export: GET /export?format&q&mode&index_version=<shown>; read headers first and abort if X-Index-Version or X-Total differ from the shown search (E3); status warning (E2) when filters.status admits non-accepted values, listing facets.status counts (never summed) - Covidence hides status from screeners (docs/results/2026-09-27-covidence-check.md); 'Importing into Covidence' disclosure EX-E7. Save: confirm dialog (public, permanent), then POST /records, then GET /records/{id} for status + methods text; STORE_FULL disables saving for the session. Record page: all values recorded (never the replay's) except the status block; drifted names each changed input and +a/-r with the paged diff; withheld/refused show no counts; mismatch renders no methods text and no export; exports disabled with reason when replay.index_version != record.index_version. API gaps for the API owner (main session to file): (1) identified_total and unclassified_total so the UI doesn't add total+excluded.total or the two unknown buckets (fallback: one unit-tested pure function); (2) default and limit clauses as text in the record (today only derivable via /parse(canonical) while query_version matches); (3) a way to read a record without a replay (?replay=false) for 429/API_BUSY.

Pre-pass fixes that land in TASK-044: compare the POST /records 201 index_version with the shown one and warn (SV-8, M3); drifted records itemise replay.excluded vs recorded when excluded_match is false (M4); track warning in the export menu (S2); same-index X-Total mismatch is a bug message, not 'index changed' (S3). BLOCKING API prerequisite for AC#1 (pre-pass S1): identified_total and unclassified_total (additive) - to be filed by the main session for the API owner. Also proposed: optional RecordRequest.index_version pin (409 like /export) and GET /records/{id}?replay=false (S4).

As built (TASK-044): lib/methods-text.ts (pure; clauses from /parse(canonical) spans, every count a record field), lib/export.ts (GET /export pinned to the shown index_version or record_id alone; headers read first: X-Index-Version differs = index changed, same index + X-Total differs = bug EX-E3b; 409 = index gone; status/track warnings from facets, never summed), lib/replay-status.ts (RC-2..RC-7, RC-3a), components/export/ (menu button with warnings as aria-describedby, record exports), components/record/ (save dialog + saved panel, record-view, methods-block, record-diff, use-record). Save posts {q, mode, index_version}; STORE_FULL disables saving for the session (sessionStorage). Record page reads ?replay=false then the replay (automatic); methods text and exports wait for the replay to settle, so mismatch never shows them; 429/API_BUSY = 'Replay: waiting' with both shown. Tests: record-fixture.json is real API answers (backend/tests/contract/record_fixture.py, checked by test_frontend_record_fixture.py); methods-text.test.ts matches the spec 05 example read from the spec file and asserts no prose number is outside the record. Smoke (production build + op serve on a copy of the local index, headless Chrome over CDP): export RIS 198/198 records, save -> 'Reproduced just now', record page reproduced with the bootstrap caution (RIS-only corpus) and no methods text, record export N1 names the record, 320 px no sideways scroll, unknown id not-found; no console errors beyond the expected 404. uv run pytest: 4651 passed, 2 skipped; npm test: 2556 passed; build, make lint, make tooling green. Worktree agents can't run backlog task complete: left In Progress for the main session.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Export menu, Save search record, /record/[id] and the PRISMA methods text (spec 05 §Components 7–8, §Pages; design E1–E4, S1–S3, R1–R6). Exports are pinned to what was shown (the search's index_version, or a record's record_id alone) and checked by headers before any byte is saved; the menu warns, with facet counts, when the export holds non-accepted statuses or non-default tracks (Covidence hides both). Save is pinned to the shown index and reads the record back for its status and methods text. The record page shows every recorded value, then the replay's status (reproduced, drifted with changes, +a/−r, re-run exclusions and a paged diff, membership-identical, could-not-be-re-run, withheld, or the blocking do-not-cite mismatch with no methods text and no export); exports are disabled with the reason when the record's index isn't here. The methods text is generated from the record and /parse(canonical), matches spec 05's example verbatim (read from the spec file in the test) and carries no number the API didn't send (tested against real API answers in record-fixture.json).
<!-- SECTION:FINAL_SUMMARY:END -->
