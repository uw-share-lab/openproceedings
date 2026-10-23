---
id: TASK-276
title: >-
  openreview_v1 _TRAILING_AND is quadratic on an author entry with a long run of
  spaces
status: In Progress
assignee: []
created_date: '2026-10-20 15:18'
updated_date: '2026-10-23 14:32'
labels:
  - ingest
dependencies: []
ordinal: 183000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by TASK-272's security sweep (2026-10-20), pre-existing: openreview_v1.py _split_entry's \s+and$ takes 791 ms on an entry with one unbroken run of 20k spaces ('a' + 20k spaces + 'b'), 11.3 s on 100k (crawl time only); 20k spaces between single words cost ~1 ms. Candidate: (?<!\s)\s+and$ (0 differences over 2M short strings).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 _TRAILING_AND is linear with identical results, with a CPU-growth test
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-23: _TRAILING_AND now (?<!\s)\s+and$ (the candidate). _AUTHOR_SEPARATOR's \s+and\s+ alternative had the same shape (344 ms on 20k spaces, run by _split_entry after _TRAILING_AND), so it gets the same anchor: ,\s*and\s+|,|(?<!\s)\s+and\s+. Tests compare _split_entry against the old patterns (swapped back on the module) over every string up to 7 characters of 'and ,\nx' (960,800); a one-off run compared each pattern alone over every string up to 8 (8.7M): no difference. Growth checks on three shapes fail on the old patterns and pass now. Tests: backend/tests/unit/ingest/test_openreview_v1_authors.py.
<!-- SECTION:NOTES:END -->
