---
id: TASK-191
title: >-
  Replace the 2026 official counts with proceedings counts when published; crawl
  NeurIPS 2026 main
status: In Progress
assignee: []
created_date: '2026-10-05 08:39'
updated_date: '2026-10-28 13:41'
labels:
  - ingest
  - eval
milestone: m-4
dependencies: []
ordinal: 135000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
coverage-sources.md's ICML 2026 main row (6,341) is a count of the conference's own paper list minus its position listing (rule 3; the lists come from OpenReview, so its Δ 0 confirms classification, not coverage); rule 1 prefers the PMLR volume once it is published. ICLR 2026's row is already rule 1 (5,351 from proceedings.iclr.cc, 2026-10-05). NeurIPS 2026's main conference was not public on OpenReview on 2026-10-05, so the index holds only its workshops; its Evaluations_and_Datasets_Track and position strings have no classifier rows yet. The skipped ICLR 2026 Workshop/Re-Align group should be checked live for another venue id.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The ICML 2026 row is replaced from the PMLR volume once it exists; NeurIPS 2026 main, D&B and position are crawled, classified with recorded fixtures and gated; Re-Align is resolved or explained
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-05 (gate, track-classifier-auditor): the ICLR 2026 proceedings index already exists and was counted that day (5,351 Conference entries at proceedings.iclr.cc/paper_files/paper/2026, equal to the index), so the ICLR row is rule 1 now. What remains: the ICML 2026 PMLR volume, NeurIPS 2026 main / D&B / position, and Workshop/Re-Align. NeurIPS 2026 on OpenReview also holds 95 Creative_AI_Track notes (other, unknown) beside its workshops.

Gate fix (2026-10-05): the ICLR 2026 main row is now rule 1, 5,351 from proceedings.iclr.cc/paper_files/paper/2026 (page sha256 recorded in coverage-sources.md; fact sheet 5,357 and retrospective 5,355 kept under Disagreements), and the coverage report is regenerated on fd13d8d27535. So for AC 1 the ICLR part is done; still pending: the ICML 2026 row from the PMLR volume once published (the current rule-3 count's lists come from OpenReview, so its Δ 0 confirms classification, not coverage), NeurIPS 2026 main / D&B / position, and Workshop/Re-Align. The description's ICLR sentence predates this.

Gate round 2 (2026-10-05, DOC-R2-N1): description and AC narrowed to what remains; the ICLR 2026 row (rule 1, 5,351) is done.

2026-10-28 (TASK-191 run). ICML 2026: the PMLR volume is v306 (v308 is the AAAI NeuroAI workshop); 6,552 entries = the fact sheet's main+position total, no track sections; row added (confirm, unknown). Crawled 6,552 records (12 abstracts refused on a title mismatch, OpenReview supplies them). The coverage row is now 6,340 = v306 entries not on the conference's position listing (213 listed, 212 in v306), replacing the rule-3 6,341; XOEVxte7Nn (main) and Pwt0TeGUE6 (position) are OpenReview-accepted but not in v306, so reconcile makes them unknown. Re-Align resolved: the group is a placeholder whose children Workshop/Re-Align/Research (67) and /Challenge (5) are the v2 venues; the crawler skipped such groups as not_a_v2_venue, which also hid NeurIPS 2025 Workshop/DBM/Findings (43) and NeurIPS 2024 Competition/LMC (9, other). Fixed: openreview_v2._child_venues lists a non-venue group's children once and crawls the venues among them (reported container); fixtures iclr-2026/group-re-align, groups-parent-re-align, notes-workshop-sub-venue. Re-crawled ICLR 2026 (22,897), NeurIPS 2024 (7,570), 2025 (10,724), 2026 (4,716; Competition is now a container too). NeurIPS 2026 main, Evaluations_and_Datasets_Track and Position_Paper_Track are NOT public yet (this part of AC 1 stays open): logged in, every accepted/rejected venueid and -/Submission invitation of the three groups returned count 0 on 2026-10-28 while the same session read the 95 Creative_AI_Track notes; proceedings.neurips.cc/paper_files/paper/2026 is 404; the conference starts 2026-12-06. Snapshot 2026-10-28-d4f4688715d0 (173,981 records; diff vs 2026-10-16-03eab0ef56c4: +890 = NeurIPS 2026 766, ICLR 2026 72, NeurIPS 2025 43, NeurIPS 2024 9; -427 = 426 NeurIPS 2026 workshop notes no longer public on OpenReview (IAB 229, Pre-to-Post 89, TTCL 79, ...) and 1 ICLR 2026 workshop rejection; changed 492, 9 of them status: the 2 ICML demotions, 2 ICLR 2026 main rejected->withdrawn, 5 NeurIPS 2026 workshop accepted->unknown). Index d9355590c4c8 (no TOKENIZER_VERSION or SCHEMA_VERSION change); parity 0 differences over 173,981 records; op eval coverage --check: M4 gate PASS, 81 of 82 gated cells within 1% plus the ICLR 2013 exception; ICML 2026 main 6,340 vs 6,340, ICLR 2026 main 5,351 vs 5,351 (docs/results/2026-10-28-coverage.md). Not promoted; release/deploy is the lead's.
<!-- SECTION:NOTES:END -->
