---
id: TASK-054
title: Coverage report and the M4 gate
status: In Progress
assignee:
  - '@jeevanp03'
created_date: '2026-09-26 01:06'
updated_date: '2026-09-29 07:36'
labels:
  - eval
milestone: m-4
dependencies:
  - TASK-048
  - TASK-049
  - TASK-051
  - TASK-052
  - TASK-053
ordinal: 53000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Spec 07 §C (coverage-reporting skill).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 docs/results/coverage-sources.md cites one official count per gated cell
- [ ] #2 Every main/D&B cell with an official count within ±1%; statuses-indexed column
- [x] #3 op eval coverage regenerates the dated report
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. op eval coverage (AC#3): open the index like op search, compute coverage with api.coverage.compute (the same data GET /coverage serves), render docs/results/<date>-coverage.md: header (date, snapshot name+hash, index_version, coverage-sources.md sha256), gate verdict, per-venue cell table (indexed accepted, official, delta, delta_pct 1dp, gate, missing abstracts, statuses indexed), gated official cells with no records as gaps (never a silent zero), cause notes for every failing cell from docs/results/coverage-causes.toml, per-listing skipped counts from the manifest, totals, the command. --check exits 1 when the gate fails.
2. First live crawl (2026-09-29, running), snapshot + index, first report; classify every miss before changing anything (AC#2).
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
TASK-002 count checks (2026-09-27): NeurIPS 2021 main proceedings 2,334 vs OpenReview v1 venues 2,630 'accepted' (2,286 poster + 284 spotlight + 60 oral) — unexplained, resolve before gating; NeurIPS 2024 main 4,034 vs 4,035. Equal: NeurIPS 2022-23 main and D&B, 2024 D&B, 2021 D&B rounds; ICML 2023-2025 PMLR vs OpenReview. Rejected counts are complete only for ICLR (decision-012).

From TASK-050: check each live crawl's counts against the venue's published numbers (the openreview-crawler agent's 1% rule) here, not in the crawler.

From TASK-052/053: the first live crawl (NeurIPS 2013-2024, ICML v28-v267) checks per-listing counts against the page's stated count and the PMLR volume table. Out of scope for now: NeurIPS competition volumes (would need spec 01 and record-schema changes, pmlr- ids are ICML-only).

From TASK-103: NeurIPS/PMLR fetches no longer follow redirects (3xx is a refusal). If the first live crawl hits one, add an on-host redirect rule to http.Policy.

From TASK-118 (2026-09-29 live dry runs): every NeurIPS listing 2013-2025 and PMLR v28-v202 matched its official count on the listing; ICML 2024-25 PMLR is track 'unknown' until OpenReview joins it. count_ok passed on 2021 D&B while 54 of 174 were dropped at the id step, so the report must also check each listing's skipped.duplicate (fixed by TASK-118).

Evidence for the note above: docs/results/2026-09-29-proceedings-dry-runs.md (per-listing listed/stated/planned/skipped vs coverage-sources.md, and the D&B collision counts).

AC#3 (2026-09-29): op eval coverage built (eval/coverage_report.py): renders api.coverage.compute's data for the index, enumerates gated official cells so a missing venue-year is a gap, cause notes from docs/results/coverage-causes.toml, listings that skipped entries, --check. Smoke run on the M2 index: 0 of 44 within ±1%, 32 gaps (expected for the literature-review subset).

Correction (2026-09-29): the smoke-run figures above (0 of 44, 32 gaps) came from an uncommitted run on the M2 index; the committed report and its figures arrive with AC#2.
<!-- SECTION:NOTES:END -->
