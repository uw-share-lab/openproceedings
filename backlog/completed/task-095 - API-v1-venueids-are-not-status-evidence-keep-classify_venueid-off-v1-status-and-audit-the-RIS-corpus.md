---
id: TASK-095
title: >-
  API v1 venueids are not status evidence: keep classify_venueid off v1 status
  and audit the RIS corpus
status: Done
assignee: []
created_date: '2026-09-27 20:49'
updated_date: '2026-09-27 21:10'
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
- [x] #1 classify.py (or the v1 adapters, TASK-051) never derives status from a v1 venue-year's bare venueid; a table test pins ICLR 2022/2023 rejected notes (fixtures under backend/tests/fixtures/http/openreview/v1/) to their venue-string status
- [x] #2 The RIS importer treats a bare venueid for a v1 venue-year as venue/year/track evidence only, or the corpus is audited and no such record is accepted without a proceedings or venue-string claim; result recorded in docs/results/
- [x] #3 openreview-api and openreview-venueids skills and spec 01 describe the rule
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
classify.is_v1 (ICLR 2013–2023, NeurIPS 2021–2022): classify_venueid gives status unknown for any venueid in a v1 venue-year; classify_v1_venue maps the exact content.venue strings seen live (research doc) to track/status, unlisted = unknown. The RIS importer labels a v1 venueid's status claim '(API v1 venue-year: not status evidence)'; a proceedings listing still decides acceptance. Fixture-driven tests read every recorded OpenReview note (V2_NOTES, V1_NOTES, completeness check). scrub.py's PERSON regex took the '@' in 'Tiny Papers @ ICLR 2023' for an email: fixed; the v1 Tiny Papers fixture's venue restored by hand; the v2 Tiny Papers 2024 and Workshop_Mexico_City fixtures still need re-recording. Audit: docs/results/2026-09-27-v1-status-audit.md — 0 of 1,805 snapshot records from a v1 venueid; dry-run re-ingest gives the same snapshot hash d5ab3d6d444a.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
v1 venueids are no longer status evidence (classify_venueid → unknown for ICLR ≤2023 / NeurIPS 2021–22; classify_v1_venue for content.venue); RIS importer, spec 01, openreview-api/venueids/track-taxonomy skills follow. Audit of snapshot 2026-09-23-d5ab3d6d444a and its scholarmend inputs: 0 records affected; dry-run rebuild byte-identical. Verified by uv run pytest, make lint, make tooling.
<!-- SECTION:FINAL_SUMMARY:END -->
