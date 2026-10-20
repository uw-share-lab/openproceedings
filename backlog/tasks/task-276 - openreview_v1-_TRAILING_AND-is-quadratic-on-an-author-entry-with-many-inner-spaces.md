---
id: TASK-276
title: >-
  openreview_v1 _TRAILING_AND is quadratic on an author entry with a long run of
  spaces
status: To Do
assignee: []
created_date: '2026-10-20 15:18'
updated_date: '2026-10-20 15:27'
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
- [ ] #1 _TRAILING_AND is linear with identical results, with a CPU-growth test
<!-- AC:END -->
