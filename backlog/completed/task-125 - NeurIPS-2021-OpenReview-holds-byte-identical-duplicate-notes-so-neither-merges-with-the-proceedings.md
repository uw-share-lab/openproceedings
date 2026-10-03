---
id: TASK-125
title: >-
  NeurIPS 2021: OpenReview holds byte-identical duplicate notes, so neither
  merges with the proceedings
status: Done
assignee:
  - '@jeevanp03'
created_date: '2026-09-29 20:52'
updated_date: '2026-09-29 21:07'
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
- [x] #1 Tests with recorded (or derived-from-recorded) notes; spec 01, the openreview-api and dedup-rules skills describe the rule
- [x] #2 On the real 2026-09-29 cache NeurIPS 2021's 300 duplicate notes collapse (297 accepted, 3 rejected) and main reaches 2,335 against the official 2,334; every other venue-year collapses 0; the 11 D&B pairs are distinct round-1 rejections resubmitted in round 2 (different pdf) and stay separate (TASK-126 lets their accepted note merge)
- [x] #3 Within one OpenReview API v1 venue-year crawl, two notes are one paper when every field but the id, forum URL and provenance is equal (title, authors, abstract, keywords, pdf, track, status, presentation, venueid) and both have a pdf and a number: the lowest-numbered note is kept and the others are counted (skipped.duplicate_submission, a non-routine skip in op eval coverage), never silently dropped; notes differing in any field stay separate
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented at the API v1 crawler (openreview_v1.collapse_duplicate_submissions), before dedup; dedup rules untouched. Rule: after a venue-year's listings, records identical in everything but id, forum URL and provenance (exact title, authors, abstract, keywords, pdf, track, status, presentation, venueid; _bibtex never reaches a record), each with a pdf, an integer note number and no crawl conflict, collapse to the lowest number; the others count in skipped.duplicate_submission (manifest, openreview_crawl_attention, DEBUG openreview_duplicate_submission; non-routine in op eval coverage). Not applied to v2: the real cache has no identical-pdf notes there, and v2 test worlds clone identical notes.
Real-cache offline replay (2026-09-29 crawl): NeurIPS 2021 3,020 notes -> 2,720 records, 300 duplicate_submission (297 accepted: 267 poster, 25 spotlight, 5 oral; 3 rejected), -K4tIyQLaY kept over BW2Z6B7S9KZ. Every other v1 and v2 venue-year collapses 0. Offline snapshot build: NeurIPS 2021 main accepted 2,335 = 2,333 merged + 1 OpenReview-only + 1 proceedings-only (official 2,334; trial had 2,929).
AC #2 not ticked: the 11 D&B pairs are NOT identical notes. They are Round 1 rejections resubmitted to Round 2 with a different pdf (OpenReview D&B holds exactly 174 accepted = official). They stay two records by rule, and dedup still leaves 11 D&B OpenReview-only + 11 proceedings-only unmerged. That needs its own decision (a follow-up task), not this rule.
combined-snapshot FILES_HASH updated: v1 crawl reports' skipped gained duplicate_submission: 0 (records and SNAPSHOT_HASH unchanged).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
OpenReview API v1 lists 300 NeurIPS 2021 papers twice: two Blind_Submission notes with different ids and numbers and identical content (title, authors, abstract, keywords, pdf, venue; only _bibtex's id differs). Dedup refused each title group as ambiguous, so neither note merged with its proceedings record: NeurIPS 2021 main was 2,929 against 2,334 (+25.5%), which also explains TASK-054's 2,630-vs-2,334 note. openreview_v1.collapse_duplicate_submissions now keeps the lowest-numbered note of notes equal in every field but id, forum URL and provenance (both with a pdf and a number) and counts the rest as skipped.duplicate_submission (non-routine in op eval coverage). On the real cache: 300 collapse (297 accepted, 3 rejected), NeurIPS 2021 main becomes 2,335 vs 2,334, every other venue-year collapses 0. The 11 D&B pairs are distinct round-1 rejections resubmitted in round 2 and stay separate (TASK-126). Track and status are compared so ICLR 2018's blind+withdrawn copies are not merged.
<!-- SECTION:FINAL_SUMMARY:END -->
