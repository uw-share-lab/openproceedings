---
id: TASK-219
title: Official accepted counts for the new venues' main cells (M4 gate rows)
status: To Do
assignee: []
created_date: '2026-10-10 03:47'
updated_date: '2026-10-10 05:35'
labels:
  - eval
  - new-venues
milestone: m-4
dependencies: []
ordinal: 152000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
No AAAI/AIES/IASEAI cell is gated (spec 07 §C): IASEAI's 92 includes 35 non-archival papers, AIES counts found so far come from the indexed source itself, AAAI figures were unsourced. Source official accepted counts and add OfficialCount rows only where the definition equals the indexed main cell and the delta is within 1%.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Each venue-year classified gateable / definition mismatch / not found, with citations
- [x] #2 Gate rows added only for gateable cells; coverage --check passes
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Milestone-A review gate (2026-10-10): every venue-year classified with citations in the research note's §Official counts (sourced 2026-10-09). Rows added to official_counts.py and docs/results/coverage-sources.md for the six gateable main cells: AIES 2024 (150) and 2025 (238); AAAI 2013 (203; gateable once the Robotics Program sections moved to main, 202 indexed), 2015 (539), 2018 (938), 2019 (1,147). Not found: AAAI 2010-2012, 2014, 2016-2017, 2020-2026 (aggregator figures only, never a row). Definition mismatch: IASEAI 2026 (92 includes 35 non-archival). AC#2's coverage --check needs a snapshot rebuilt with the Robotics move (AAAI 2013 main is 191 on b2d8b4a79c0a, 202 after); the AAAI 2020-2026 official counts may exist in chairs' slides or AAAI press releases.

Round 2 (2026-10-10): the snapshot is rebuilt (988e342c9c07, index 0c731ce2eb5b) and docs/results/2026-10-10-coverage.md passes the gate at 77 of 78 gated cells, six of them the new AAAI and AIES rows (AAAI 2013 main is 202 against 203). AC#2 done. Remaining, outside this task's ACs: official counts for AAAI 2010-2012, 2014, 2016-2017 and 2020-2026 are not found (aggregator figures only).
<!-- SECTION:NOTES:END -->
