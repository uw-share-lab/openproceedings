---
id: TASK-189
title: 'Dedup: the title step never consults the abstract'
status: Done
assignee: []
created_date: '2026-10-05 08:39'
updated_date: '2026-10-06 00:26'
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
- [x] #1 Either a title-step merge of an import is refused when its own-page abstract matches a different record of the cell, or the cases are documented as accepted with their reason; tests for both shapes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Failing unit tests in test_dedup.py: shape A (-Guard joins $R^2$-Guard by abstract, not Guard by title), shape A without the abstract's holder (title merge stands), shape B (two RIS rows, one title, different abstracts, merge), the main/workshop shared-abstract shape (same and other workshop title: import merges with the main note), and an import whose abstract's holder can't take it (stays apart, rows).
2. dedup.py: step 2 sets aside an import (decision-045) whose own-page abstract key a crawled cluster of the venue-year keeps and no title partner does (_yields_to_its_abstract, from _abstract_buckets); _refusals reports it the same way on the output records.
3. test_dedup_props.py: property that an import joined by title keeps no own abstract a crawled record holds unless a partner in its record holds it.
4. Docs: dedup.py docstring, spec 01, dedup-rules skill; notes say the real-cache rebuild is still to be measured.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-05: stopped for an owner decision (none recorded). Both shapes reproduced on v011/dedup: (A) note $R^2$-Guard (abstract L), note Guard (abstract O), import -Guard with own-page abstract L -> import merges with Guard by title_venue_year; (B) forum-id RIS row and proceedings-id RIS row, one title, abstracts L and O -> merge by title. Proposed rule for the owner: refuse a title-step merge of an imported cluster when it keeps an own-page abstract key that no title partner keeps and a crawled record of the same venue-year does (then step 3 joins it to that record). A plain 'matches a different record' test would wrongly refuse a paper whose main note and workshop note share the abstract (14 such pairs on the 2026-10-05 crawl). Shape B: propose accepting as is (OpenReview and camera-ready abstracts differ legitimately), refused only under the rule above. Effect on the real cache must be measured with a rebuild (no data/ in the worktree).

Implemented per decision-045. dedup.py: _yields_to_its_abstract (step 2 leaves an imported record out of a title group when a crawler gave a record of its venue-year the import's own-page abstract and no title partner keeps it), _crawled_abstracts (crawler claims only: a RIS row's abstract in a crawled cluster can be replaced by a same-step merge; the 2,000-example run found that idempotence break, pinned as YIELD_TO_A_REPLACED_RIS_ABSTRACT), _refusals reports a yielded import as a title_key ambiguous_not_merged row. Tests: shape A (-Guard joins $R^2$-Guard by abstract), shape A without the holder (title merge stands), shape B (two RIS rows still merge), main/workshop shared-abstract shape (same and other workshop title: merges with the main note), holder that step 3 can't take (import stays apart, rows), RIS-row holder ignored; property test_an_import_joined_by_its_title_keeps_no_abstract_only_another_crawled_record_holds (fails on the pre-change code). test_an_import_that_matched_by_title_is_not_matched_again_by_abstract now gives the main note the import's abstract (its old shape is the decision-045 yield, covered by the stays-apart test). Runs: test_dedup.py 207, test_dedup_props.py 11 at dev and at ci (2,000), ingest unit dir 1651, make tooling green. STILL TO DO: the real-cache rebuild under this rule is not measured (no data/ in the worktree); the main session runs it and records the effect here.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
decision-045 implemented: dedup's title step leaves an imported record out of a title-key group when a crawler gave a record of the same venue-year the import's own-page abstract and none of its title partners keeps it; step 3 then joins it to that record when it may, else it stays apart with a title_key row. Two RIS rows with one title and different abstracts, and an import beside a main note and its workshop version sharing the abstract, merge as before. Holders are read from crawler abstracts only, for idempotence. Spec 01, the dedup-rules skill and dedup.py docstrings updated. The real-cache rebuild is still to be measured by the main session.
<!-- SECTION:FINAL_SUMMARY:END -->
