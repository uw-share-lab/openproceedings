---
id: TASK-273
title: >-
  doi_key's unquote of a percent-encoded doi.org link costs ~20x its length in
  memory
status: In Progress
assignee:
  - '@jeevanparmar'
created_date: '2026-10-20 15:03'
updated_date: '2026-10-25 02:50'
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
- [x] #1 doi_key's memory on a percent-encoded link is bounded at the largest line /compare accepts (capped unquoting or a lower MAX_COMPARE_LINE, with a peak_bytes test), or the bound is documented in spec 07 with the owner's decision
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-24: owner chose capped unquoting. The trailing run is read raw or encoded and never unquoted; a path longer than 12*MAX_DOI returns None unread; a key past caps.MAX_DOI names no record. 16 MB line: 329 MB -> 33.6 MB peak; frozen-copy equality property (3,000 examples) + peak_bytes test at 16 MB; 12 hand mutants caught. Spec 07 updated.
<!-- SECTION:NOTES:END -->
