---
id: TASK-272
title: >-
  DOI pattern held backtracking state per registrant part (CI timing failure on
  a 1 MB hostile value)
status: In Progress
assignee: []
created_date: '2026-10-20 14:42'
updated_date: '2026-10-20 15:02'
labels:
  - eval
  - security
  - ci
dependencies: []
ordinal: 179000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
test_doi_key_is_linear_on_a_hostile_value[registrant] failed twice on PR #175's CI on 2026-10-20 (ratio 10.3 and 11.3 for 4x the size; limit 8). _DOI's greedy (?:\.\d+)* backtracks over every '.N' of a 1 MB '10.1.1.…1./x!' before refusing it; Python's re keeps state for each (63 MB peak), so the cost was memory-bound and runner-dependent (locally ~4.2x). doi_key reads a reviewer's uploaded file in /compare.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 _DOI's registrant quantifiers are possessive (no backtracking can change its outcome), equivalent on a 200k-string random sample
- [x] #2 A test bounds doi_key's peak memory on the 1 MB registrant (tracemalloc, not time), failing on the old pattern (62.8 MB) and passing on the new (~0)
- [x] #3 spec 07's /compare hostile-value note says so
- [x] #4 The same greedy-repeat shape on crawled input is possessive too: record._doi (Urls.doi) and html.py's _CUSTOM_OR_NAMESPACED and _HYPHENATED, each with a peak_bytes test that fails on the old pattern (62.8 MB)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Gate round 1 (code-reviewer) found the same shape in ingest/record.py _doi and ingest/sources/html.py's two name patterns (62.8 MB each on a 1 MB value); fixed in this PR with tests/timing.py peak_bytes (refuses an outer trace).
<!-- SECTION:NOTES:END -->
