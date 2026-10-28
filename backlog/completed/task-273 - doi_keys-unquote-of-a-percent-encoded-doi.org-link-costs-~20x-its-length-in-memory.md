---
id: TASK-273
title: >-
  doi_key's unquote of a percent-encoded doi.org link costs ~20x its length in
  memory
status: Done
assignee:
  - '@jeevanparmar'
created_date: '2026-10-20 15:03'
updated_date: '2026-10-26 13:07'
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

2026-10-25 (review rounds 1 and 2): the 329 MB -> 33.6 MB figure above held only for a bare link (docs-reviewer S1). Round 1 reads a link by position (pattern match with pos/endpos, str.count with bounds, one reversed slice): its one copy is the path reversed, 16.8 MB peak at MAX_COMPARE_LINE (16 MiB, 16,777,216 characters) whether bare, labelled or padded (was 33.6/50.3/67.1 MB). Round 2: a value that is no link was still sliced, rstripped and had its closing ')'s added back (up to 3 copies, 50.3 MB). Past caps.MAX_DOI characters only the trailing run and whitespace may follow, so the rest is checked in place and only the first MAX_DOI characters are sliced: under 0.1 MB on every no-link shape. The link branch skips trailing whitespace on its reversed copy, so rstrip no longer copies the line. Measured in docs/results/2026-10-24-doi-key-memory.md (old, round 1, round 2, now). test_doi_key_reads_the_largest_compare_line_in_bounded_memory: links under 1.1x the line, no-link values (padded, labelled, trailing '.', unbalanced '(...))', and review-methodologist's shapes) under 0.1 MB (an absolute bound, 100,000 bytes). Equivalence: frozen-copy property plus examples at the cap; exactness-guardian's diff_doi.py 0 diffs over 700,000 random values (against round 1 and against the pre-fix function), its link boundary sweep 0, and a 9,900-case no-link sweep around MAX_DOI 0 under the cap rule.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
doi_key reads a value by position. A link's one copy is its path reversed (16.8 MB at MAX_COMPARE_LINE, 16 MiB, against 329 MB before), and a value with no link is keyed from its first caps.MAX_DOI characters plus a bounded scan (under 0.1 MB). Keys are identical to before (700,000 random values and boundary sweeps, 0 diffs). A bounded-memory test holds links under 1.1x the line and no-link values under 0.1 MB. docs/results/2026-10-24-doi-key-memory.md.
<!-- SECTION:FINAL_SUMMARY:END -->
