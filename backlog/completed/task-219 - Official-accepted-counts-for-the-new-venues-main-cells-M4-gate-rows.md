---
id: TASK-219
title: Official accepted counts for the new venues' main cells (M4 gate rows)
status: Done
assignee: []
created_date: '2026-10-10 03:47'
updated_date: '2026-10-10 19:55'
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

Round 3 (2026-10-10): six more gate rows, each a count of AAAI's own published accepted-paper list (no AAAI document states an accepted count for these years; the controller's ruling for the owner: the list must be independent of the OJS proceedings and its definition our main cell within 1%; each description says 'counted' and names the list): AAAI 2010 (262), 2012 (292), 2014 (398), 2017 (637), 2020 (1,614), 2021 (1,696). op eval coverage --check on index 99c2e7ea2a0a (snapshot 2026-10-10-21779e017036) passes, 83 of 84 gated cells within 1% (deltas 0, +2, 0, +2, -4, -2) plus the ICLR 2013 exception. Not gated, each with a cited note on /coverage and in the report (TASK-222): AAAI 2011 (definition mismatch: the list's 240 omit the Robotics Program, we hold 248), AAAI 2016 (the list appears derived from the proceedings, so a gate would be circular), AAAI 2022-2026 (not found: chairs' emails quoted on third-party sites and aggregator figures only, apparently the main technical track alone), IASEAI 2026 (definition mismatch).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Every new-venue main cell is classified with citations. Gated: AIES 2024, 2025 and AAAI 2013, 2015, 2018, 2019 (stated counts) plus AAAI 2010, 2012, 2014, 2017, 2020, 2021 (counts of AAAI's own accepted-paper lists); coverage --check passes at 83 of 84 gated cells. AAAI 2011, 2016, 2022-2026 and IASEAI 2026 are not gated and carry cited notes.
<!-- SECTION:FINAL_SUMMARY:END -->
