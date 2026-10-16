---
id: TASK-234
title: >-
  Re-check the AAAI 2021 gate row: where its 40 AI for Social Impact papers were
  counted
status: In Progress
assignee: []
created_date: '2026-10-11 05:08'
updated_date: '2026-10-16 15:51'
labels:
  - coverage
  - new-venues
dependencies: []
priority: medium
ordinal: 163000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The AAAI 2021 main gate row (official_counts.py, coverage-sources.md) counts 1,656 main technical papers plus 40 AI for Social Impact, but cites only AAAI's Main Technical Track PDF; where the 40 were counted was not recorded (hci-researcher and review-methodologist, gate C round 1). Find AAAI's own AI for Social Impact accepted list for 2021 (aaai.org, or an archived copy), check it says it was made before the proceedings, and cite it in the row; if it can't be found, the row's count or its gating must change.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The 2021 row cites the list its 40 AI for Social Impact papers were counted from, with the date it was read, in official_counts.py and coverage-sources.md
- [x] #2 If no such AAAI list is found, the row is re-counted from the main-track PDF alone or moved to an ungated note, and the coverage report regenerated
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-16: the 40 AI for Social Impact papers are the cited PDF's own last section ('Special Track on AI for Social Impact', pp. 121-124; its first page says that list 'appears at the end of this document'); 1,656 main technical before it. No separate AISI list among the Internet Archive's 887 aaai.org/Conferences/AAAI-21/ URLs. The cited copy was first archived 2021-11-10 (embedded creation date 2021-01-29); an earlier copy archived 2020-12-30, before the conference, has the same 40 and 1,657 main technical (paper 7140 dropped later). Row keeps 1,696 (independent by count difference) and names the earlier copy; accessed 2026-10-16. Against the earlier copy it would be 1,697 (delta -3, 0.18%), still passing. AC2 not needed (the list was found); count unchanged, so the coverage report needs no regeneration.

AC2 is conditional and does not apply: the list was found (the 40 are the cited PDF's own last section), so the row is not re-counted or ungated and the coverage report needs no regeneration. Review round 1: the row now cites the capture counted and both digests; which copy to count (1,696 or 1,697) is reported to the lead as an owner choice.
<!-- SECTION:NOTES:END -->
