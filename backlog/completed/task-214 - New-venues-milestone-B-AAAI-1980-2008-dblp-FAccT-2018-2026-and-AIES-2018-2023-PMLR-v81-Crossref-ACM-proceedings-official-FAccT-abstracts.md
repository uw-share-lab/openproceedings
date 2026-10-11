---
id: TASK-214
title: >-
  New venues milestone B: AAAI 1980-2008 (dblp), FAccT 2018-2026 and AIES
  2018-2023 (PMLR v81, Crossref ACM proceedings), official FAccT abstracts
status: Done
assignee: []
created_date: '2026-10-10 03:47'
updated_date: '2026-10-10 10:37'
labels:
  - ingest
  - new-venues
milestone: m-4
dependencies: []
ordinal: 147000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Milestone B of docs/plans/2026-10-09-new-venues-design.md (decision-049): AAAI 1980-2008 from the pinned dblp release (dblp_aaai.toml), sources/crossref.py + acm_proceedings.toml for FAccT 2019-2026 and AIES 2018-2023, PMLR v81 for FAccT 2018, sources/facct_site.py for the official 2022/2025/2026 FAccT abstracts. Facts: docs/research/2026-10-09-aaai-aies-facct-iaseai-sources.md.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Every venue-year in the design's B rows is indexed with counts equal to its table's verified count (a mismatch stops the crawl)
- [x] #2 Every new record names itself through urls.native and its abstract attribution links the paper's page
- [x] #3 Snapshot diff shows additions only; full parity 0; coverage --check passes; docs as built
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Milestone B built on feat/new-venues-b: AAAI 1980-2008 from the pinned dblp release (4,730 records, 23 held years; AAAI also not held in 1995), FAccT 2018 from PMLR v81 (17) and 2019-2026 from Crossref (1,213; FAccT 2020's 26 tutorial/CRAFT entries counted as not papers), AIES 2018-2023 from Crossref (575), official FAccT abstracts by exact join (2022 169/181, 2025 206/206, 2026 298/314). Record schema 7. Also fixed a pre-existing dedup idempotence bug (TASK-179 era). Real data: snapshot 2026-10-10-21779e017036 (173,292; +6,535, 0 changed), index 99c2e7ea2a0a, parity 0, coverage PASS.
<!-- SECTION:FINAL_SUMMARY:END -->
