---
id: TASK-053
title: PMLR miner and ICML volume table
status: Done
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-09-27 21:34'
labels:
  - ingest
milestone: m-4
dependencies:
  - TASK-022
  - TASK-002
ordinal: 52000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
ICML 2013-2022 primary (v28, v32, v37, v48, v70, v80, v97, v119, v139, v162; decision-013) and confirmation of 2023+ (v202, v235, v267) (pmlr-proceedings skill).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Volume table in config, each row with a source; unknown volumes never coerced to ICML
- [x] #2 Competition/workshop volumes classified correctly
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Volume table as data: ingest/pmlr_volumes.toml (number, venue, year, track, role primary|confirm|out_of_scope, papers, heading, index_title, verified, source), loaded and validated by volumes.py; ICML_PMLR_VOLUMES derived (ICML primary/confirm rows only), so RIS/urls keep one table. 2. Add v28-v97 (RIS now imports PMLR URLs in those volumes as ICML; test the change) and the NeurIPS competition + ICML/NeurIPS workshop volumes as out_of_scope rows (never main, never ingested). 3. PMLR miner ingest/sources/pmlr.py: volume index (heading checked against the table) + per-paper pages via the shared cached, rate-limited fetcher (ingest/sources/http.py), cache under data/cache/pmlr. 4. op ingest pmlr --year Y [--dry-run|--offline]; snapshot build mines completed crawls offline. 5. Fixture tests only (no network).
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
TASK-002 verified each ICML volume's heading and paper count (pmlr-proceedings skill table); add v28-v97 to the volume config; NeurIPS competition volumes v123/v133/v176/v220 need a NeurIPS table (ICML_PMLR_VOLUMES is ICML-only). v235 paper entries link OpenReview forum ids. Fixtures: backend/tests/fixtures/http/pmlr/.

pmlr_volumes.toml (31 rows: 13 ICML ingested v28-v267 with role primary/confirm, papers, heading, index_title, verified, source; NeurIPS competition v123/v133/v176/v220 and ICML/NeurIPS workshop volumes as out_of_scope rows) loaded + validated by volumes.py; ICML_PMLR_VOLUMES derived. RIS behaviour change (tested): a pmlr_url in v28-v97 now imports as ICML 2013-2019 main instead of skipping as no_id/out_of_scope; competition/workshop/unlisted volumes still never import. ingest/sources/pmlr.py: refuses unlisted/out_of_scope volumes and a page heading the table does not name; per-volume index + paper pages via the shared fetcher; claims source pmlr with the table row as venue/year/track evidence; v235 OpenReview link -> urls.forum. op ingest pmlr --year Y (year -> volume via the table; 2026 refused). NeurIPS competition volumes are not ingested: spec 01 lists PMLR for ICML only and pmlr- natives are ICML-only (schema). No live crawl was run.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
PMLR volume table moved to data (ingest/pmlr_volumes.toml, validated by volumes.py; ICML v28-v267 with role/papers/heading/index title/verified/source, competition and workshop volumes as out_of_scope rows); ICML_PMLR_VOLUMES derived, so RIS now imports PMLR URLs in v28-v97 (tested). PMLR miner (ingest/sources/pmlr.py): table-gated volumes only, heading check, volume index + paper pages via the shared fetcher, claims source pmlr, v235 OpenReview link as urls.forum; op ingest pmlr --year Y. Verified with backend/tests/unit/ingest/test_pmlr.py and test_ris.py (recorded fixtures only), full uv run pytest, make lint, make tooling. No live crawl run.
<!-- SECTION:FINAL_SUMMARY:END -->
