---
id: TASK-273
title: >-
  doi_key's unquote of a percent-encoded doi.org link costs ~20x its length in
  memory
status: To Do
assignee: []
created_date: '2026-10-20 15:03'
updated_date: '2026-10-20 15:05'
labels:
  - eval
  - security
dependencies: []
ordinal: 180000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found in TASK-272's review (qa+security, 2026-10-20): urllib's unquote builds a list of fragments, so https://doi.org/10.1/ + '%2e' x 333k peaked at 19.6 MB / 169 ms. Harmless at /compare's default 32,768-character line cap (~0.7 MB), but at the operator maximum MAX_COMPARE_LINE (1<<24) one line costs ~311 MB and 2.9 s, past api/config.py's ~250 MB per-file budget. Not a regex issue; needs a choice between capping the unquoted span, lowering MAX_COMPARE_LINE, or documenting the bound.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 doi_key's memory on a percent-encoded link is bounded at the largest line /compare accepts (capped unquoting or a lower MAX_COMPARE_LINE, with a peak_bytes test), or the bound is documented in spec 07 with the owner's decision
<!-- AC:END -->
