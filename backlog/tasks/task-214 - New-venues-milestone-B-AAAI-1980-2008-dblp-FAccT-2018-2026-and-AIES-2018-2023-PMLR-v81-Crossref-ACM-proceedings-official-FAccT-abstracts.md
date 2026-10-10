---
id: TASK-214
title: >-
  New venues milestone B: AAAI 1980-2008 (dblp), FAccT 2018-2026 and AIES
  2018-2023 (PMLR v81, Crossref ACM proceedings), official FAccT abstracts
status: To Do
assignee: []
created_date: '2026-10-10 03:47'
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
- [ ] #1 Every venue-year in the design's B rows is indexed with counts equal to its table's verified count (a mismatch stops the crawl)
- [ ] #2 Every new record names itself through urls.native and its abstract attribution links the paper's page
- [ ] #3 Snapshot diff shows additions only; full parity 0; coverage --check passes; docs as built
<!-- AC:END -->
