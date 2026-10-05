---
id: TASK-178
title: Crawl the 2026 venue-years from OpenReview and rebuild the snapshot and index
status: In Progress
assignee: []
created_date: '2026-10-05 02:43'
labels:
  - ingest
  - eval
milestone: m-4
dependencies: []
references:
  - docs/specs/01-ingestion.md
  - docs/specs/07-evaluation.md
ordinal: 122000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The first live crawl (2026-09-29) stopped at 2025. The index holds ICLR 2026 (415 records) and ICML 2026 (111) only as imports from the Trust-Evals RIS, and NeurIPS 2026 not at all, so for 2026 a search can only return papers the review's Google Scholar search already found, and the Scholar comparison (TASK-056) matches 530 Scholar records against their own import. The review's criteria centre on 2025-2026. Found 2026-10-04 by TASK-056's review; the owner approved the crawl the same day.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 ICLR 2026, ICML 2026 and, if OpenReview has published it, NeurIPS 2026 are crawled; every venueid and presentation string the crawl met is classified or reported, none silently defaulted (01 track taxonomy)
- [ ] #2 A new snapshot and index are built; the snapshot diff against 2026-09-29-d552baa07aed is reviewed and shows the RIS-only 2026 records merging into crawled ones or explains each that does not
- [ ] #3 The coverage report is regenerated on the new index with a sourced official count for each 2026 cell that has one, and the M4 gate result stated (07 section C)
- [ ] #4 The Scholar comparison is re-run on the new index and its RIS-only share reported (07 section B)
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Detached crawl from the main checkout: data/crawl-logs/run-2026.sh (op ingest openreview --venue ICLR|ICML|NeurIPS --years 2026, sequential), started 2026-10-05T02:42Z; status lines in data/crawl-logs/status. 2. Read each report for unparseable venueids or presentation strings (spec 01 lists ICLR 2026 Oral and ICML 2026 spotlight as seen but unrecorded) and fix the classifier with recorded fixtures if needed. 3. op snapshot build, op snapshot diff against 2026-09-29-d552baa07aed, op index build, op index parity. 4. op eval coverage; add official 2026 accepted counts to coverage-sources.md where published. 5. Re-run op eval scholar on the new index (TASK-056).
<!-- SECTION:PLAN:END -->
