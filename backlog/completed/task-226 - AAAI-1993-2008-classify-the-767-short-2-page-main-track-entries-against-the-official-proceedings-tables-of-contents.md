---
id: TASK-226
title: >-
  AAAI 1993-2008: classify the 767 short (<=2 page) main-track entries against
  the official proceedings tables of contents
status: Done
assignee: []
created_date: '2026-10-10 14:28'
updated_date: '2026-10-10 15:20'
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
Built: 47 [[section]] rows (report-226's 40 + 7 IAAI ranges for 2000, 2002, 2004-2008, from the official AAAI/IAAI contents; iaai04/iaai05contents.php read from Wayback 2013 captures, every dblp entry in each range matched an IAAI heading but BarishKCMPS00, which the 2000 IAAI page skips), 12 invited-talk not_paper rows, 1 [[track]] row (BlackH06). LimCKO00's and AhmadiS06a's planned key rows are not needed: their start pages (1020, 1853) are in their ranges. Unresolved, stay main: Sultanik05, Thornton05 (and WangL05, 4 pp., same gap); the IAAI papers in the 1996-1999 volumes (blocks of 21/32/22/17 entries no AAAI contents page lists; their IAAI contents pages were not read: follow-up). Counts: 891 moved (749 from the report + 142 IAAI), 21 removed incl. TASK-225's. Snapshot 2026-10-10-df9a9f8b2143 vs 2026-10-10-21779e017036: changed 999 (track only: AAAI 891, AIES 108), removed 39 (AAAI 21, AIES 18), added 0, provenance_only 0, rekeyed 0.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
dblp_aaai.toml gained [[section]] (47) and [[track]] (1) tables plus 12 invited-talk not_paper rows (dblp_aaai_table.py, dblp_aaai.py): each of the 767 has an official-contents track or is listed unresolved (Sultanik05, Thornton05). Verified by unit tests, test_track_rules_replay.py over the pinned release, and op snapshot diff (2026-10-10-df9a9f8b2143 vs 21779e017036): only track changes and the expected removals. Decision-050.
<!-- SECTION:FINAL_SUMMARY:END -->
