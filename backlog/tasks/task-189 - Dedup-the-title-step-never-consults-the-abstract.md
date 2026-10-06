---
id: TASK-189
title: 'Dedup: the title step never consults the abstract'
status: To Do
assignee: []
created_date: '2026-10-05 08:39'
updated_date: '2026-10-06 00:04'
labels:
  - ingest
  - dedup
milestone: m-4
dependencies: []
ordinal: 133000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found reviewing TASK-179 (no real instance today): an import whose title lost a symbol can equal a different paper's title key in the same venue-year (-Guard beside a note titled Guard) and merges on title though its abstract is another record's. Also, a forum-id RIS row and a proceedings-id RIS row with one title and different long abstracts now merge.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Either a title-step merge of an import is refused when its own-page abstract matches a different record of the cell, or the cases are documented as accepted with their reason; tests for both shapes
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-05: stopped for an owner decision (none recorded). Both shapes reproduced on v011/dedup: (A) note $R^2$-Guard (abstract L), note Guard (abstract O), import -Guard with own-page abstract L -> import merges with Guard by title_venue_year; (B) forum-id RIS row and proceedings-id RIS row, one title, abstracts L and O -> merge by title. Proposed rule for the owner: refuse a title-step merge of an imported cluster when it keeps an own-page abstract key that no title partner keeps and a crawled record of the same venue-year does (then step 3 joins it to that record). A plain 'matches a different record' test would wrongly refuse a paper whose main note and workshop note share the abstract (14 such pairs on the 2026-10-05 crawl). Shape B: propose accepting as is (OpenReview and camera-ready abstracts differ legitimately), refused only under the rule above. Effect on the real cache must be measured with a rebuild (no data/ in the worktree).
<!-- SECTION:NOTES:END -->
