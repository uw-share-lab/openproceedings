---
id: TASK-130
title: >-
  Decide and enforce who answers track in a venue-year on OpenReview
  (decision-005 track precedence)
status: Done
assignee:
  - '@jeevanp03'
created_date: '2026-09-29 23:23'
updated_date: '2026-09-30 02:21'
labels:
  - dedup
  - decision
dependencies: []
ordinal: 114000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-005 says proceedings answer track only for venue-years not on OpenReview. TASK-072 (2026-09-29) did not enforce it: on the real crawl 151 records in venue-years on OpenReview take their track from the proceedings, and setting them to unknown would drop ICLR 2016 main from 80 to 0 (OpenReview holds only its workshop track) and ICLR 2014 main to 34/35. Needs the owner's decision: does 'on OpenReview' mean the venue-year or the venue-year's track, and what is a listing's track when OpenReview holds the track but not the paper. decision-005 §Track in an OpenReview venue-year records the question.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The owner's answer is recorded in decision-005 (or a superseding decision)
- [x] #2 dedup/reconcile enforce it with unit and property tests; the real-crawl effect per gated cell is listed
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Owner's decision (2026-09-29): 'on OpenReview' is per track. Recorded in decision-005 (track row + §Track in an OpenReview venue-year: per track), evidence numbers kept. Operationally 'OpenReview holds the track' is read per record: an OpenReview track claim is the note's own content.venueid, so a record carrying one is on a held track and wins (PRECEDENCE, OpenReview first); a record with none takes its listing's track. OpenReview crawlers claim no proceedings URL and _mergeable keeps a note on a non-proceedings track (unknown included) apart from every listing, so wherever both answer OpenReview's track is a proceedings track. Current precedence already behaved exactly so: no logic change, a comment in dedup.py plus tests: test_dedup.py (ICLR 2016 archive main keeps main; OpenReview-held track beats the listing incl. D&B/main both ways, PMLR unknown, ICLR 2014 agree; a listing OpenReview doesn't hold keeps its own track in an OR-held track; an OR unknown note never merges into a listing), test_dedup_props.py (track rule property over pools; ICLR_2016 example in idempotence), test_reconcile.py (ICLR 2016 through reconcile, idempotent). Real data: scratch rebuild = snapshot 2026-09-29-4cd2bba17cad, records.jsonl byte-identical; 0 cells change; 149 proceedings-track records unchanged; op eval coverage M4 gate PASS 43/44 + ICLR 2013 exception. Spec 01, dedup-rules and record-schema skills, results doc updated.

Review round 1 (2026-09-29): owner's second answer recorded in decision-005 (a paper with no OpenReview note on a track OpenReview holds takes its listing's track; 69 records: ICLR 2014 main 1, NeurIPS main/D&B 4, NeurIPS 2025 Creative AI 64; the strict reading would have made them unknown, ICLR 2014 main 34/35, failing the gate). 'The proceedings don't host' reworded to 'a track outside PROCEEDINGS_TRACKS' (NeurIPS proceedings do host Creative AI). Follow-up, not yet a task: possible Creative AI double count. NeurIPS 2025 Creative AI listings (track other, outside PROCEEDINGS_TRACKS) never merge with their OpenReview notes (track_not_merged), so a Creative AI paper can be two records; other is not default-filtered in and not gated, so no reported count moves, but a search with track:other would show both.

Review round 2 (2d52b9a): approved. The older TASK-126 'the proceedings don't host' wording (dedup.py:12-320, spec 01:186) is left for the Creative AI follow-up.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
decision-005 records both owner answers (2026-09-29): 'on OpenReview' is per track (ICLR 2016 main keeps its 80 archive papers), and on a track OpenReview holds, a paper with no OpenReview note takes its listing's track (69 records). No logic change: precedence already behaved so; tests in test_dedup, test_dedup_props and test_reconcile pin it. Real data: byte-identical snapshot 4cd2bba17cad, 0 records changed, gate PASS.
<!-- SECTION:FINAL_SUMMARY:END -->
