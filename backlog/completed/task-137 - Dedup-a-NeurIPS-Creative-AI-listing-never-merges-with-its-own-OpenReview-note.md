---
id: TASK-137
title: 'Dedup: a NeurIPS Creative AI listing never merges with its own OpenReview note'
status: Done
assignee:
  - '@jeevanp03'
created_date: '2026-09-30 02:40'
updated_date: '2026-09-30 04:47'
labels:
  - dedup
  - bug
milestone: m-4
dependencies: []
ordinal: 120000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by TASK-130's review (2026-09-29). NeurIPS proceedings host Creative AI (track other), but PROCEEDINGS_TRACKS leaves 'other' out, so dedup never merges a Creative AI listing with its own OpenReview note (NeurIPS.cc/<Y>/Creative_AI_Track venueid): one paper can be two records. The 2026-09-29 crawl has 64 Creative AI listings in NeurIPS 2025 (docs/results/2026-09-29-reconcile-real-data.md). 'other' is outside the default filter and not gated, so no reported count moves, but a track:other search shows both. Also tidy the older TASK-126 wording 'the proceedings don't host' (dedup.py docstrings, spec 01 §Pipeline 4).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Decide whether Creative AI listings may merge with their own OpenReview notes, and record it (dedup-rules; decision-005 if precedence changes)
- [x] #2 If yes: dedup merges them with unit and property tests, and the other never-merge rules stay intact
- [x] #3 Real-data check: Creative AI records per year before and after; the coverage gate unchanged
- [x] #4 dedup.py's docstrings and spec 01 §Pipeline 4 no longer say the proceedings don't host 'other'
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Decision (AC1): decided by the owner, 2026-09-30: a NeurIPS Creative AI listing merges with its own OpenReview note; other `other` tracks still never merge. Recorded in decision-005 (amended 2026-09-30) and in dedup-rules §Never merge. The narrow implementation below is the implementer's.

Design: `other` is NOT only Creative AI. NeurIPS 2025 also has 54 Education_Program notes, and the venueid table has High_School_Projects_Track, Competition/LMC and out-of-window forms. So PROCEEDINGS_TRACKS and reconcile are unchanged, and `other` is still never a covered track. Dedup's track rule is now per family (`_family`): a merge that involves a listing holds only PROCEEDINGS_TRACKS records (a listing's own `unknown` included), or only NeurIPS Creative AI records (`dedup.is_creative_ai`). A record counts as Creative AI when every source claiming its track says `other` and backs it with Creative AI evidence of the record's year: the venueid (`classify.is_creative_ai_venueid`, bare or with a status suffix) or a `-Creative_AI_Track` proceedings URL. TASK-126's set-aside is per family: a Creative AI note next to a main-only listing is set aside, and so is a main note next to a Creative-AI-only listing. Every other never-merge rule is unchanged and pinned by tests (workshop, tiny_papers, blogpost, competition, evidence-less other, a note's unknown, against main and Creative AI listings).

Tests: test_dedup.py §TASK-137 (merge, RIS copy, rejected note alone, 9 never-merge cases, 12 other-track cases, set-aside in both directions, two notes are ambiguous); test_venueid.py CREATIVE_AI table; test_dedup_props.py `creative` strategy with its own property, added to pools, plus the never-folds and track properties extended (passes at 2,000 examples); test_reconcile.py (Creative AI is never judged).

Real data (AC3; full write-up with commands in docs/results/2026-09-30-creative-ai-merge.md), scratch snapshots before 2026-09-29-c6c9a156fdf7 (origin/dev a48e453) and after 2026-09-29-78f5a0204501, same cache:
- 59 of the 64 NeurIPS 2025 Creative AI listings merged with their notes (58 proceedings+OpenReview, 1 proceedings+OpenReview+RIS). Two of them merged past a same-title workshop note that is now set aside.
- 5 remain listing-only: 4 have no matching note, and 1 (LUMIA) matches two Creative AI notes, so it is ambiguous.
- Counts: records 95,936 → 95,877; merges 28,272 → 28,331 (+59 title_venue_year, NeurIPS 2025); conflicts 7,815 → 7,815 (+59 status precedence:neurips_proceedings, −61 track_not_merged, +2 ambiguous_not_merged).
- The only changed cell is NeurIPS 2025 other/unknown, 146 → 87. other/accepted stays 64, and no other cell moved.
- All 59 changed records are Creative AI; the 59 vanished ids are exactly the new merged_ids.
- op eval coverage --check: PASS, 43 of 44 plus the accepted exception, identical before and after.

Checks: full backend suite 5,643 passed, 2 skipped; make lint and make tooling green. Wording (AC4): 'the proceedings don't host' is gone from the dedup.py docstrings, spec 01 §Pipeline 4 and the dedup-rules and prisma-reporting skills, replaced by the track rule; small notes were added to the track-taxonomy, openreview-venueids and neurips-proceedings skills.

Review round (2026-09-30): owner's dated decision recorded in decision-005 and here; results doc added and linked; never-merge rows for a Creative AI URL from another year and for a source whose own evidence disagrees (Creative AI URL, Education_Program venueid: pins the all()); is_creative_ai docstring notes that sources without a track claim aren't checked.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
A NeurIPS Creative AI proceedings listing now merges with its own OpenReview note (decided by the owner, 2026-09-30); other `other` tracks still never merge. Dedup's track rule is per family: a merge involving a listing holds only PROCEEDINGS_TRACKS records or only NeurIPS Creative AI records, admitted by their own evidence (the Creative_AI_Track venueid or proceedings URL of the record's year, every track-claiming source agreeing). PROCEEDINGS_TRACKS and reconcile are unchanged. Unit, table and property tests pin the merge and every other never-merge rule. Real crawl: 59 of 64 NeurIPS 2025 Creative AI listings merge (4 have no note; LUMIA is ambiguous), NeurIPS 2025 other/unknown 146 → 87, no other cell moves, M4 gate PASS unchanged (docs/results/2026-09-30-creative-ai-merge.md; decision-005 amended).
<!-- SECTION:FINAL_SUMMARY:END -->
