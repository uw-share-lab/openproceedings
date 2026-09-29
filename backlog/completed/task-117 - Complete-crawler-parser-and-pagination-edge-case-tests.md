---
id: TASK-117
title: Complete crawler parser and pagination edge-case tests
status: Done
assignee:
  - '@jeevanp03'
created_date: '2026-09-28 02:00'
updated_date: '2026-09-29 08:20'
labels:
  - ingest
  - tests
milestone: m-4
dependencies: []
references:
  - backend/tests/unit/ingest/test_iclr.py
  - backend/tests/unit/ingest/test_pmlr.py
  - backend/tests/unit/ingest/test_openreview_v1.py
  - backend/tests/unit/ingest/test_openreview_v2.py
priority: low
type: task
ordinal: 113000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The final M4 QA review found several low-risk branches that are implemented and indirectly covered by recorded fixtures or adjacent guards, but lack direct compact regressions. Add targeted tests without changing crawler behavior unless a test exposes a defect.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 ICLR and PMLR parsers have compact reordered/single-quoted attribute and decoy-element cases
- [x] #2 OpenReview v1 and v2 reject a multi-page listing whose count changes between pages
- [x] #3 OpenReview v1 and v2 count exact semantic cross-listing duplicates nonfatally while conflicting duplicates remain fatal
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
NeurIPS decoy authors and reordered attributes, OpenReview /groups projection, and MAX_ELEMENTS were added during the review; this task covers the remaining QA Should findings.

Tests only; no defect found. AC1: test_iclr.py list-page (2015) and paragraph-page (2014) cases, test_pmlr.py index+heading case, each with single-quoted/reordered attributes and decoy links, sections or classes. AC2: v1/v2 multi-page listing whose first page states count 4 and the second 3 (rows 3) is refused; killed the mutant that drops the len(counts) > 1 guard. AC3: v1 (NeurIPS 2021 D&B Round1+Round2) and v2 (accepted note also in Rejected_Submission) parametrized: identical record -> skipped[duplicate]=1 with the first listing's claims kept; changed title -> CrawlError; killed the mutant that stops counting duplicates.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Direct regressions for the crawler branches the M4 QA review found only indirectly covered; no behaviour change and no defect found. ICLR (list and paragraph pages) and PMLR index parsers: single-quoted, reordered attributes and decoy elements. OpenReview v1 and v2: a multi-page listing whose count changes between pages is refused; a note in two listings is a counted duplicate only when its record is identical (provenance aside), and a conflicting copy is a CrawlError. Each new guard test was checked to fail with its guard removed. make test and make lint green.
<!-- SECTION:FINAL_SUMMARY:END -->
