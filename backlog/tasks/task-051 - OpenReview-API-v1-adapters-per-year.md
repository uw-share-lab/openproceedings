---
id: TASK-051
title: OpenReview API v1 adapters per year
status: To Do
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-09-27 20:49'
labels:
  - ingest
milestone: m-4
dependencies:
  - TASK-048
  - TASK-049
  - TASK-050
ordinal: 50000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
ICLR 2013, 2014, 2016-2023 (decision-013 moved the start from 2018) and NeurIPS 2021-2022 incl. D&B; decisions as separate notes or venue strings. Per-year status carriers are in the openreview-api skill §API v1 (TASK-002).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 One adapter per schema variant with a recorded fixture
- [ ] #2 Rejected/withdrawn statuses captured (decision per task q2-status)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
TASK-002: the bare v1 venueid is on rejected papers too (ICLR 2017/2022/2023, NeurIPS 2021-22, D&B 2021) — status only from content.venue / decision note / withdrawn and desk-rejected invitations (TASK-091). ICLR 2013 status+track from content.decision; 2014 and 2016 have no decisions (unknown). v1 invitation filters must be prefix regexes; fetch decisions per forum. Fixtures: backend/tests/fixtures/http/openreview/v1/.

Renumbered 2026-09-27 (parallel-branch id collision): TASK-090 → TASK-094, TASK-091 → TASK-095, TASK-092 → TASK-096 in the notes above.
<!-- SECTION:NOTES:END -->
