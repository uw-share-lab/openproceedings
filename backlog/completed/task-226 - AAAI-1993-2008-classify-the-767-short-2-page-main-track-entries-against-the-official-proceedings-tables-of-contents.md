---
id: TASK-226
title: >-
  AAAI 1993-2008: classify the 767 short (<=2 page) main-track entries against
  the official proceedings tables of contents
status: Done
assignee: []
created_date: '2026-10-10 14:28'
updated_date: '2026-10-10 16:16'
labels:
  - data
  - aaai
dependencies: []
ordinal: 159000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-224/225 evidence (2026-10-10) found 767 AAAI main-track entries from 1993-2008 of two pages or fewer, mostly in trailing student-abstract, poster and demo blocks of each volume. Find an official AAAI table of contents per year (AAAI digital library, aaai.org proceedings pages, or the printed front matter), map each block to a track (student_abstract, demo, other, not a paper), and encode it as per-year page-range rules in dblp_aaai.toml so offline replay stays deterministic. Owner asked for this on 2026-10-10.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Each of the 767 entries has a track backed by a cited official table of contents, or is listed as unresolved with the reason
- [x] #2 Rules live in the pinned table, with replay tests; op snapshot diff reports only track changes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Ruling 3: dblp_aaai.toml gains [[section]] (year, page range, track, label, verified, source) and [[track]] (key) tables, read by dblp_aaai_table.py and dblp_aaai.py; report-226's 40 ranges + 12 invited-talk not_paper rows; robot sections other; IAAI papers of the 2000-2008 volumes as iaai ranges where the official AAAI/IAAI contents separate them; unit tests, a replay test over the pinned release (fixtures/pinned/aaai-main-pages.json), a real snapshot and op snapshot diff, docs.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Built: 57 [[section]] rows (report-226's 40; 11 IAAI ranges for 1996-2000, 2002, 2004-2008 from the official AAAI and IAAI contents pages, every dblp entry in each range matched an IAAI entry by start page and title; 6 'other' ranges for 2006-2008's NECTAR and Senior Member Papers, as the owner decided for 2010+ in TASK-218), 12 invited-talk not_paper rows, 19 [[track]] rows (BlackH06's page typo; 2006's 18 AAAI Member Abstracts, which dblp gives no pages, as other). LimCKO00's and AhmadiS06a's planned key rows are not needed (start pages 1020, 1853 inside their ranges). BarishKCMPS00 is iaai: the IAAI-2000 page lists it first under Emerging Applications without a page number. 2005's demo and robot sections are on aaai05contents.php without page numbers; ranges from the entries' paper pages. A main-key entry of a sectioned year with no readable start page and no row now stops the replay (unplaced_page). Unresolved, stay main: Sultanik05, Thornton05, WangL05 (on no official page). Counts: 1,089 AAAI entries moved, 21 removed incl. TASK-225's. Snapshot 2026-10-10-9efa49481112 vs 2026-10-10-21779e017036: changed 1,197 (track only: AAAI 1,089, AIES 108), removed 39 (AAAI 21, AIES 18), provenance_only 377 (AIES main evidence corrected), added 0, rekeyed 0.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
dblp_aaai.toml gained [[section]] (57) and [[track]] (19) tables plus 12 invited-talk not_paper rows (dblp_aaai_table.py, dblp_aaai.py; page_ranges.py shared with the ACM table): each of the 767 has an official-contents track or is listed unresolved (Sultanik05, Thornton05), and the review added the IAAI 1996-1999, NECTAR/Senior Member and AAAI Member Abstract rows. AAAI 1980-2008: 3,567 main, 399 student_abstract, 158 consortium, 127 demo, 232 iaai, 173 other, 53 workshop. Verified by unit tests, test_track_rules_replay.py over the pinned release, and op snapshot diff (2026-10-10-9efa49481112 vs 21779e017036): only track changes, the expected removals and the AIES evidence correction. Decision-050.
<!-- SECTION:FINAL_SUMMARY:END -->
