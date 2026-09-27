---
id: TASK-095
title: >-
  API v1 venueids are not status evidence: keep classify_venueid off v1 status
  and audit the RIS corpus
status: To Do
assignee: []
created_date: '2026-09-27 20:49'
labels:
  - ingest
  - classify
milestone: m-4
dependencies: []
priority: high
ordinal: 92000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-002 found (docs/research/2026-09-27-openreview-and-proceedings-facts.md §How status is represented) that OpenReview API v1 puts the bare venue path on rejected submissions: ICLR.cc/2017/conference (245 rejected, plus workshop invitations), ICLR.cc/2022/Conference (1,523 'ICLR 2022 Submitted'), ICLR.cc/2023/Conference (2,219 'Submitted to ICLR 2023'), NeurIPS.cc/2021/Conference and 2022 (opt-in rejected), NeurIPS.cc/2021/Track/Datasets_and_Benchmarks/Round1 (78 rejected), ICLR.cc/2023/TinyPapers and BlogPosts. classify_venueid reads e.g. ICLR.cc/2022/Conference as main/accepted. In v1 years status must come from content.venue or the decision note. The M2 RIS importer takes scholarmend venueid claims at face value, so a rejected ICLR 2022/2023 paper could be in the M2 corpus as accepted.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 classify.py (or the v1 adapters, TASK-051) never derives status from a v1 venue-year's bare venueid; a table test pins ICLR 2022/2023 rejected notes (fixtures under backend/tests/fixtures/http/openreview/v1/) to their venue-string status
- [ ] #2 The RIS importer treats a bare venueid for a v1 venue-year as venue/year/track evidence only, or the corpus is audited and no such record is accepted without a proceedings or venue-string claim; result recorded in docs/results/
- [ ] #3 openreview-api and openreview-venueids skills and spec 01 describe the rule
<!-- AC:END -->
