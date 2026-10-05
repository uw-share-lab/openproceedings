---
id: TASK-177
title: Compare a query's results against a reviewer's own RIS set
status: In Progress
assignee: []
created_date: '2026-10-05 01:47'
updated_date: '2026-10-05 05:06'
labels:
  - api
  - frontend
  - eval
  - ux
milestone: m-3
dependencies:
  - TASK-056
references:
  - docs/specs/07-evaluation.md
  - docs/specs/04-backend-api.md
ordinal: 121000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
A reviewer moving from Google Scholar to openproceedings asks what they lose and gain: which of the records they already hold does this query keep, which does it drop, and which does it add. On 2026-10-04 this was answered for the Trust-Evals review by script (51 kept, 1,754 dropped, 16 added). TASK-056 builds the matching and classification for the report; this task makes the same comparison available to any user for their own RIS file.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Given a RIS file and a query, the user sees the counts and lists of records kept, dropped and added, with records matched to the index by the merge rules of spec 01, and records that are not in the index reported separately
- [x] #2 The comparison reuses TASK-056's matching code; there is one implementation
- [ ] #3 An upload is size- and record-capped, parsed without executing or storing it, never logged (logging-standards), and reviewed by security-reviewer; the design says whether it runs in the CLI only or also on a public instance, and why
- [x] #4 The comparison never changes the query's result set (00 guarantee 5), and the kept, dropped and added lists are exportable
- [x] #5 Specs and help as built
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Built on branch task-177-ris-compare (off feat/review-comparison-tools).

- API: POST /api/v1/compare?q=&mode= with the RIS file as the raw body (application/x-research-info-systems). One answer: total (= /search's), the file's accounting, kept / dropped / not_in_index / added / not_compared with reason, detail, matched_by, independent; reason_totals; each list as CSV text and the added papers as RIS. api/compare.py is transport over eval/scholar_compare.py (compare_query gained a tick hook; result_in_scope and only_in_result were factored out of it).
- Operator-controlled: ApiConfig.compare_enabled, off by default; op serve turns it on for a loopback host without a trusted proxy, or with --compare. Off: 403 API_COMPARE_DISABLED, /meta limits.compare null, no match table, the path reads no body over 64 KiB.
- Caps (in /meta limits.compare): 16 MiB body, 5,000 records, 64 lines per allowed record, 32,768 characters a line, 1,000 a title or venue line, 5,000 result papers the file lacks, 60 s of work, 30 s to arrive, 1 comparison at a time. Cost: export_weight + the query's verified charge + one token per 500 ms the slot was held.
- Match table: built once per served index in a background thread after the swap, held on the Served bundle.
- Web: components/compare/compare-records.tsx on the search page, drawn only when limits.compare is not null.
- AC#3 is left unchecked only for its last clause: security-reviewer has not reviewed this yet (the review gate is the main session's). Everything else in it is built and tested (backend/tests/contract/test_compare.py).
- Measured on index 05a0541717f6 with the review's export (1,834 records) and its $ string: 51 kept, 1,756 dropped, 8 not in the index, 16 added, 19 not compared; 20 to 24 s.
<!-- SECTION:NOTES:END -->
