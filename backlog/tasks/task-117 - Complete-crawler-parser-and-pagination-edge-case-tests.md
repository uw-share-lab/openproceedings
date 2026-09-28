---
id: TASK-117
title: Complete crawler parser and pagination edge-case tests
status: To Do
assignee: []
created_date: '2026-09-28 02:00'
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
- [ ] #1 ICLR and PMLR parsers have compact reordered/single-quoted attribute and decoy-element cases
- [ ] #2 OpenReview v1 and v2 reject a multi-page listing whose count changes between pages
- [ ] #3 OpenReview v1 and v2 count exact semantic cross-listing duplicates nonfatally while conflicting duplicates remain fatal
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
NeurIPS decoy authors and reordered attributes, OpenReview /groups projection, and MAX_ELEMENTS were added during the review; this task covers the remaining QA Should findings.
<!-- SECTION:NOTES:END -->
