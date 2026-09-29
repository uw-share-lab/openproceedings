---
id: TASK-126
title: >-
  Dedup: a candidate that cannot be the listed paper makes a title group
  ambiguous, so real pairs never merge
status: In Progress
assignee:
  - '@jeevanp03'
created_date: '2026-09-29 21:08'
updated_date: '2026-09-29 21:27'
labels:
  - dedup
  - bug
milestone: m-4
dependencies: []
priority: high
ordinal: 111000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The first full crawl's coverage trial (2026-09-29): NeurIPS 2023 main 3,252 vs 3,218 official and 2024 4,086 vs 4,034, because each unmerged proceedings record's title group also holds an accepted workshop OpenReview paper of the same title (2023: 32 groups; 2024: 42). NeurIPS 2021 D&B (185 vs 174) has 11 groups where a round-1 rejected OpenReview note shares the title of its round-2 accepted resubmission (different pdf, TASK-125). Dedup counts these as rival OpenReview candidates and refuses the whole group as ambiguous_not_merged, although neither can be the listed (proceedings) paper: the track rule never merges a workshop paper into a proceedings record, and proceedings list only accepted papers. Projected: 2023 main 3,218 (= official), 2024 main 4,035 (0.02%), 2021 D&B 174.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 In dedup's title-key step, a group containing a listed (proceedings) cluster excludes, as rivals, clusters that cannot be that listed paper: track-incompatible (the existing track rule) or status not accepted/unknown; the rest merge if otherwise mergeable, and the excluded clusters stay separate records; a group with two mergeable accepted OpenReview submissions still refuses
- [x] #2 Unit and property tests (test_dedup, test_dedup_props) pin the rule and its limits; merges.csv/conflicts.csv rows stay right (the excluded clusters' refusal is still reported)
- [x] #3 On the real 2026-09-29 cache (read-only replay into a scratch data dir) NeurIPS 2023/2024 main and 2021 D&B groups merge and reach their official counts ±1%; the change of every other cell is listed and explained
- [x] #4 The dedup-rules skill (and decision-005 if it states the rule) describe it
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
As built (dedup.py `_merging`, `_not_the_listed_paper`): when a title group is refused and holds a listing, the non-listing clusters that can't be the listed paper are set aside and the rest are judged again by `_mergeable`; they merge if it passes. Set aside: a track the proceedings don't host (the `_mergeable` track rule; a listing is never set aside) or a status of rejected/withdrawn/desk_rejected. Two deliberate differences from a literal "mirror the track rule": (1) a non-listing `unknown` track is NOT set aside, since it waits for evidence and may be the listed paper; like an `unknown` status it stays a rival, so the group still refuses. (2) Status only breaks a rivalry: the whole group is tried first, so a lone rejected note still merges with its listing (decision-005: the proceedings decide status; an existing test pins it). The chain re-check still judges the whole chained group with `_mergeable`, which is stricter than or equal to the per-key rule, so a set-aside cluster that another key chains in with a listing splits the chain. `_refusals` reports each set-aside cluster against the first listing of its group, as track_not_merged (track) or ambiguous_not_merged (status); the rest are reported as before. No new resolution value was added. Decision-005 doesn't state the ambiguity rule, so it's unchanged; the dedup-rules skill and spec 01 §Pipeline 4 describe the rule.

Real-cache replay (2026-09-29 cache, read-only, scratch data dirs; the baseline was built from the TASK-125 HEAD source): the M4 gate went from 36/44 to 43/44. 212 new title_venue_year merges, none removed, and records fell from 96,152 to 95,940. Per cell, indexed accepted (base -> new, official): NeurIPS 2021 D&B 185->174 (174; 11 rejected round-1 notes); 2023 main 3,252->3,219 (3,218; 33, one group with 4 workshop notes); 2023 D&B 326->324 (322); 2024 main 4,086->4,035 (4,034; 51); 2024 D&B 466->459 (459); 2025 main 5,381->5,287 (5,286; 94); 2025 D&B 503->498 (497); 2025 position 42->40 (not gated); ICLR 2024 main 2,262->2,261 (2,260) and 2025 main 3,712->3,706 (3,703), each an iclr_archive listing plus its main note plus a same-title accepted workshop note. Every merge outside NeurIPS 2021 D&B was blocked only by accepted workshop notes. Every set-aside record has its conflicts.csv row, and rerunning dedup on the 437 affected records gives no merges and the same ids. The only cell still failing is ICLR 2013 main (unchanged).
<!-- SECTION:NOTES:END -->
