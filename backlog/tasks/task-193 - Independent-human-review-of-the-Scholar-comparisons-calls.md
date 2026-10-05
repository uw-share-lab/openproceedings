---
id: TASK-193
title: Independent human review of the Scholar comparison's calls
status: To Do
assignee: []
created_date: '2026-10-05 08:39'
updated_date: '2026-10-05 13:02'
labels:
  - eval
  - research
milestone: m-4
dependencies: []
ordinal: 137000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The 48 calls in docs/results/2026-10-05-scholar-comparison-review.csv were made by an AI assistant at the owner's direction, with evidence in each note; none of the 538 spot-check rows has a call. A result the paper cites should rest on a reviewer's own reading of at least a sample.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A reviewer (role stated) confirms or corrects the 48 calls and calls a stated sample of the spot-check rows; the report is regenerated and its notes say who made which calls; any our_bug is investigated
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Gate (2026-10-05, review-methodologist, docs-reviewer, hci-researcher): this task need not block merging the code, but it BLOCKS citing the 48 calls (and the report's counts after the calls) in the paper and treating spec 07 §B as closed. What the assistant did and did not check: for the 12 scholar_missed papers it checked only that no record with the title is in mended.ris or the review's other Scholar files (17 raw Scholar exports and 3 pre-filter output files; 21 files with mended.ris); it did not read the abstracts, and relied on the tool's evidence that the query's tokens are in the title or abstract: the reviewer must redo that part first. No spot-check row of the 538 has a call, so the full_text headline has no human sample.

Gate fix (2026-10-05): the report now prints each distinct reviewer_role with its row count beside the Human calls figures, on the closing line and on the command's verdict line, and an after-the-calls table per query; the 2026-10-05 "classified: yes" rests on these AI-assistant calls and is provisional until this task's reviewer replaces the role on each row they repeat.
<!-- SECTION:NOTES:END -->
