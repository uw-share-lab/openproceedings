---
id: TASK-125
title: >-
  NeurIPS 2021: OpenReview holds byte-identical duplicate notes, so neither
  merges with the proceedings
status: In Progress
assignee:
  - '@jeevanp03'
created_date: '2026-09-29 20:52'
updated_date: '2026-09-29 21:02'
labels:
  - ingest
  - dedup
  - bug
milestone: m-4
dependencies: []
priority: high
ordinal: 111000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The first full crawl's coverage trial (2026-09-29) had NeurIPS 2021 main at 2,929 accepted against the official 2,334 (+25.5%), and D&B at 185 vs 174. OpenReview v1 lists 297 main (and 11 D&B) papers twice: two Blind_Submission notes with different ids and numbers (e.g. -K4tIyQLaY #292 and BW2Z6B7S9KZ #8244) whose content is identical (title, authors, abstract, keywords and the same pdf) apart from the id in _bibtex. Dedup then sees two OpenReview submissions with one title, refuses the group as ambiguous (403 title_key ambiguous_not_merged rows), and the proceedings record merges with neither: 2,036 merged + 595 OpenReview-only + 298 proceedings-only. This is also the TASK-054 note's unexplained 2,630 OpenReview-accepted vs 2,334 (2,334 + 297 duplicates). No other venue-year has identical-pdf duplicates in the trial (their same-title groups have different pdfs: distinct submissions).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Within one OpenReview venue-year crawl, notes whose content is identical (same pdf, title, authors, abstract) are one paper: the lowest-numbered note is kept and the others are counted in the crawl report (not silently dropped); notes that differ in any of those stay separate
- [ ] #2 On the trial data NeurIPS 2021's duplicates collapse (297 main, 11 D&B) and their proceedings records merge; no other venue-year changes
- [x] #3 Tests with recorded (or derived-from-recorded) notes; spec 01, the openreview-api and dedup-rules skills describe the rule
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented at the API v1 crawler (openreview_v1.collapse_duplicate_submissions), before dedup; dedup rules untouched. Rule: after a venue-year's listings, records identical in everything but id, forum URL and provenance (exact title, authors, abstract, keywords, pdf, track, status, presentation, venueid; _bibtex never reaches a record), each with a pdf, an integer note number and no crawl conflict, collapse to the lowest number; the others count in skipped.duplicate_submission (manifest, openreview_crawl_attention, DEBUG openreview_duplicate_submission; non-routine in op eval coverage). Not applied to v2: the real cache has no identical-pdf notes there, and v2 test worlds clone identical notes.
Real-cache offline replay (2026-09-29 crawl): NeurIPS 2021 3,020 notes -> 2,720 records, 300 duplicate_submission (297 accepted: 267 poster, 25 spotlight, 5 oral; 3 rejected), -K4tIyQLaY kept over BW2Z6B7S9KZ. Every other v1 and v2 venue-year collapses 0. Offline snapshot build: NeurIPS 2021 main accepted 2,335 = 2,333 merged + 1 OpenReview-only + 1 proceedings-only (official 2,334; trial had 2,929).
AC #2 not ticked: the 11 D&B pairs are NOT identical notes. They are Round 1 rejections resubmitted to Round 2 with a different pdf (OpenReview D&B holds exactly 174 accepted = official). They stay two records by rule, and dedup still leaves 11 D&B OpenReview-only + 11 proceedings-only unmerged. That needs its own decision (a follow-up task), not this rule.
combined-snapshot FILES_HASH updated: v1 crawl reports' skipped gained duplicate_submission: 0 (records and SNAPSHOT_HASH unchanged).
<!-- SECTION:NOTES:END -->
