---
id: TASK-224
title: >-
  Owner review: AIES 2018-2023 short entries (student abstracts, keynotes) sit
  in track main
status: Done
assignee: []
created_date: '2026-10-10 10:37'
updated_date: '2026-10-10 16:16'
labels:
  - ingest
  - new-venues
milestone: m-4
dependencies: []
ordinal: 157000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Crossref carries no section data, so the 141 AIES 2018-2023 entries of two pages or fewer stay main (about 20 front-of-volume keynotes, 96 student abstracts, 25 short in-sequence papers; listed in docs/research/2026-10-09-aaai-aies-facct-iaseai-sources.md). From 2024 OJS labels student abstracts student_abstract, so the default search treats the two eras differently. Decide whether to add not_paper rows (keynotes) in ingest/acm_proceedings.toml, which are rows, and whether to give student abstracts the student_abstract track, which is a design change: the table has no track column (every Crossref record is main, decision-049), so it would gain one (a per-DOI track override) with a code and spec change. An official source for each row either way.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Owner decision recorded; table rows added if any, with evidence
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Ruling 1 (controller for the owner, 2026-10-10): acm_proceedings.toml gains a [[section]] table (venue, year, page range, track, label, verified, source) read by acm_table.py and crossref.py; 5 AIES student-abstract ranges; 18 keynote [[not_paper]] rows; unit tests, a replay test over the pinned Crossref pages (fixtures/pinned/aies-2018-2023-pages.json), docs.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Built per ruling 1 with one deviation: 2023's range pp. 939-1012 holds 31 works (the 19 short ones plus 12 student entries of 3-6 pages between them), so 108 student_abstract, not 96: the ruling's mechanism is start-page ranges, the track taxonomy forbids page-count rules, and ruling 3 accepts range-caught longer entries for AAAI. 18 keynote not_paper rows; .3375839 and .3462443 stay main. Snapshot 2026-10-10-df9a9f8b2143 vs 2026-10-10-21779e017036: AIES 108 track changes, 18 removals, nothing else. Decision-050.

Review rulings: 108 (not 96) is accepted, since the contents-page range wins, as in ruling 3. AIES main claims in sectioned proceedings name the pages they fall outside (377 provenance-only changes; AIES 2020 has no section row and keeps its wording). A sectioned proceedings' work with no readable start page now stops the crawl (unplaced_page). Snapshot 2026-10-10-9efa49481112.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
acm_proceedings.toml gained [[section]] rows (acm_table.py, crossref.py): AIES 2018-2023 student abstract blocks are student_abstract (108: 19/20/0/7/31/31, all inferred from page position), 18 keynotes not_paper (557 records). Verified by unit tests, test_track_rules_replay.py over the cached Crossref pages, and op snapshot diff (2026-10-10-9efa49481112 vs 21779e017036): AIES 108 track changes, 18 removals, 377 provenance-only (the corrected main evidence).
<!-- SECTION:FINAL_SUMMARY:END -->
