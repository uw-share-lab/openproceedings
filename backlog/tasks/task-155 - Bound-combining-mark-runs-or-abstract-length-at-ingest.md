---
id: TASK-155
title: Bound combining-mark runs or abstract length at ingest
status: To Do
assignee: []
created_date: '2026-10-01 12:29'
labels:
  - security
  - ingest
dependencies: []
references:
  - backend/src/openproceedings/query/normalize.py
priority: low
ordinal: 130000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Source: TASK-067 review gate (security-reviewer). CPython's own NFKC/NFC canonical reordering stays superlinear when combining classes alternate: `a` + `\u0301\u0338` x n tokenizes in about 2 s at 80k characters and 15 s at 200k (measured 2026-10-01, after TASK-067 made the tokenizer's own scan linear). `q` is capped at 2,000 code points, but a stored abstract has no length cap, so a hostile abstract would cost every search that highlights it and the index build. Fix: cap a run of combining marks, or an abstract's length, at ingest. Either changes snapshot content (and so snapshot_hash and index_version), so it needs a decision on the cap.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A decision records the cap (mark-run length or abstract length) and what happens to text over it (truncated, refused, or reported)
- [ ] #2 Ingest applies the cap, with a test of a hostile mark-heavy abstract, and the snapshot manifest reports the records it changed
- [ ] #3 Tokenizing the largest abstract the cap allows stays under a stated time budget (a CPU-time ratio test like test_a_run_of_marks_is_linear)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Needs an owner decision on the cap. Deferred from the TASK-067 review gate.
<!-- SECTION:NOTES:END -->
