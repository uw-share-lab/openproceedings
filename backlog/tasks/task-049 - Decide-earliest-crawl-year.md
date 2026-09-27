---
id: TASK-049
title: 'Decide: earliest crawl year'
status: In Progress
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-09-27 20:42'
labels:
  - decision
milestone: m-4
dependencies: []
ordinal: 48000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Spec 00 open question 3. Proposal: crawl from 2018 and filter by year: in the query.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 backlog decision recorded
- [x] #2 Spec 00 §Open questions Q3 closed; spec 01 §Sources year ranges updated
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Owner decision 2026-09-27 recorded as decision-013: crawl from 2013 (ICLR's first year) wherever a source has the venue-year. The proposal's premise (ICLR on OpenReview from 2018) was wrong: v1 holds ICLR 2013, 2014, 2016-2023; 2015 is absent, 2014 has no decisions, 2016 only the workshop track (TASK-092). Spec 00 Q3 closed; spec 01 §Sources year ranges and a crawl-window paragraph; spec 04 §Exports parenthetical updated.

Worktree sandbox refused 'backlog task complete' (2026-09-27); all ACs ticked and final summary written — main session: set Done and complete after merge.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Decided (owner, 2026-09-27): crawl every venue from 2013 where a spec 01 source holds the venue-year; year ranges stay in the query. decision-013; spec 00 Q3 closed; spec 01 §Sources gives per-source ranges from 2013 (ICLR v1 2013/2014/2016-2023, NeurIPS proceedings 2013+, PMLR v28+). Gaps (ICLR 2014 status, 2015, 2016 conference) are TASK-092.
<!-- SECTION:FINAL_SUMMARY:END -->
