---
id: TASK-137
title: 'Dedup: a NeurIPS Creative AI listing never merges with its own OpenReview note'
status: To Do
assignee:
  - '@jeevanp03'
created_date: '2026-09-30 02:40'
updated_date: '2026-09-30 02:43'
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
- [ ] #1 Decide whether Creative AI listings may merge with their own OpenReview notes, and record it (dedup-rules; decision-005 if precedence changes)
- [ ] #2 If yes: dedup merges them with unit and property tests, and the other never-merge rules stay intact
- [ ] #3 Real-data check: Creative AI records per year before and after; the coverage gate unchanged
- [ ] #4 dedup.py's docstrings and spec 01 §Pipeline 4 no longer say the proceedings don't host 'other'
<!-- AC:END -->
