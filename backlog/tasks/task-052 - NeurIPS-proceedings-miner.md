---
id: TASK-052
title: NeurIPS proceedings miner
status: In Progress
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-09-27 21:19'
labels:
  - ingest
milestone: m-4
dependencies:
  - TASK-022
  - TASK-002
ordinal: 51000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
proceedings.neurips.cc main and D&B (neurips-proceedings skill).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 ≤2023 Datasets_and_Benchmarks alias handled
- [x] #2 Cross-checks OpenReview acceptance; conflicts to conflicts.csv
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Shared fetcher ingest/sources/http.py: disk page cache keyed by URL (atomic writes, fixture-shaped entries, 404s cached), polite pacing, 429/5xx retries honouring Retry-After, other 4xx raise, host allow-list, offline mode. 2. NeurIPS miner ingest/sources/neurips.py: year index (+ the 2021 D&B host), track by host/year/token (token-less <=2021 main from host+year; round1/round2 on the D&B host; Datasets_and_Benchmarks alias <=2023), abstract pages (citation_title must match, block tags to spaces, double-escape decode, LaTeX verbatim), accepted status, claims with cache fetch times; stated-vs-listed count check. 3. op ingest neurips --year Y [--dry-run|--offline]; crawl marker under data/cache/neurips/crawls; snapshot build re-mines completed years offline, so the proceedings/OpenReview cross-check runs through dedup (status/track rows in conflicts.csv). 4. Fixture tests only.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
TASK-002: 1987-2021 main URLs have no track token (-Abstract.html; classify_proceedings('') is unknown, so main comes from host+year); 2022-23 token Datasets_and_Benchmarks, 2024 _Track; 2021 D&B on datasets-benchmarks-proceedings.neurips.cc (round1 66, round2 108). 2025 main/D&B not published on 2026-09-27 (only 64 Creative AI). Crawl from 2013 (decision-013). Fixtures: backend/tests/fixtures/http/neurips/.

Built ingest/sources/ (http.py cached polite fetcher: page cache keyed by URL, atomic fixture-shaped entries with fetched_at, 1 req/s default, 429/5xx retries honouring Retry-After/ratelimit-reset, other 4xx raise, truncation retried, host allow-list, offline mode; neurips.py miner; crawl.py ingest + offline re-mine; common.py reports/markers). Track rules in classify.classify_neurips_listing (token-less <=2021 main by host+year; D&B host round1/round2; Datasets_and_Benchmarks alias <=2023 only; unknown otherwise, counted + listing_attention). urls.py now parses the 2021 D&B host (tokens with digits); ris.py checks NeurIPS listing tokens with the same rules. op ingest neurips --year Y[-Y] [--dry-run|--offline] [--refresh] [--delay>=0.5]; markers under data/cache/neurips/crawls; op snapshot build re-mines marked years offline and adds sources.neurips_proceedings (crawl_window + per-listing stated/listed/count_ok, tracks, abstract_missing split into title_mismatch/page_missing). Cross-check: proceedings records merge with OpenReview records in dedup; status precedence neurips_proceedings, track precedence OpenReview; disagreements are conflicts.csv rows (test_proceedings_cross_check_openreview_through_dedup). Not built here: OpenReview-accepted-but-unlisted -> unknown (TASK-072), the OpenReview crawler itself (TASK-050). Finding: the 2025 year page links a separate /paper_files/paper/2025/vol38-main-conference volume; reported as see_also (warning), not crawled until recorded. No live crawl was run.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
NeurIPS proceedings miner (ingest/sources/neurips.py) over a shared cached, polite, resumable fetcher (sources/http.py); op ingest neurips --year Y[-Y] with --dry-run/--offline/--refresh/--delay; crawl markers + offline re-mine in op snapshot build (sources.neurips_proceedings in the manifest). Tracks by host/year/token (classify_neurips_listing; <=2023 D&B alias; 2021 D&B host rounds; unknown counted), accepted status, claims with cache fetch times, citation_title-gated abstracts. Cross-check through dedup (proceedings decide acceptance, OpenReview the track, disagreements to conflicts.csv). Verified with backend/tests/unit/ingest/test_neurips.py and test_fetch.py (recorded fixtures only, no network), full uv run pytest, make lint, make tooling. No live crawl run.
<!-- SECTION:FINAL_SUMMARY:END -->
