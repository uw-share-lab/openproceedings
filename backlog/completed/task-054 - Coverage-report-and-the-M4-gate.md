---
id: TASK-054
title: Coverage report and the M4 gate
status: Done
assignee:
  - '@jeevanp03'
created_date: '2026-09-26 01:06'
updated_date: '2026-09-30 00:32'
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
- [x] #1 docs/results/coverage-sources.md cites one official count per gated cell
- [x] #2 Every main/D&B cell with an official count within ±1%; statuses-indexed column
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

Part 2 (2026-09-29): owner-accepted exceptions in the gate. docs/results/coverage-causes.toml takes an optional ["<Venue> <year> <track>".accepted] table under a cell's cause: indexed, official (the exact counts accepted), reason, papers, accepted_by (a role), accepted_on (a TOML date), decision (decision-<n>); every key required, unknown keys refused (load_cause_file). gate() passes an outside-±1% cell as accepted only while both counts equal the exception's; any drift fails it as 'drifted' (the cause note shows accepted vs observed), and a gap is never accepted. The report marks the cell '✓ accepted exception', counts exceptions in the verdict line, lists each under 'Owner-accepted exceptions', and reports stale ones (cell within ±1% or not gated); op eval coverage names each on stderr, logs accepted_exceptions/stale_exceptions, and --check treats a matched exception as passing. ICLR 2013 main (23 vs 24; Factorized Topic Models, 11y_SldoumvZl, is on ICLR's 2013 conference list but OpenReview decides it a workshop poster) is the first, per decision-016. Spec 07 §C and the coverage-reporting skill state the rule. AC#2 still waits on the real-data report once dev has all crawler fixes.

Part 2 review (2026-09-29): an exception now passes only if its papers are the gap as well as its counts matching: len(papers) == |official - indexed|, each a record id in the index's snapshot (op eval coverage looks them up in the RecordFile), outside the cell for an under-count (inside it for an over-count); otherwise the cell fails as drifted with the failed check in its note. A gap cell with an exception stays 'gap' (note says why). A stale exception fails --check. Loading refuses control characters, non-record-id or repeated papers, accepted_by outside {project owner}, and (at runtime) a decision with no backlog/decisions record. load_causes removed; the CLI's official table is injected via cli._official_table. Spec 00 M4 row, spec 07 §C (API reports raw ±1%; the exception is applied only by op eval coverage), the skill, coverage-auditor, /coverage, coverage-sources.md and decision-016 updated.

AC#1/AC#2 (2026-09-29, real data): report docs/results/2026-09-29-coverage.md, snapshot 2026-09-29-4cd2bba17cad (snapshot_hash 4cd2bba17cad0b7bcd1d73a4bcaa868ba52c40a7fce30a33a4a84725c521f27e), index_version b170674bcf49, built offline from the main checkout's data/cache (read-only) at dev 6a5a0fd; the same snapshot hash as TASK-072's build, so the build reproduced. op eval coverage --check exits 0: M4 gate PASS, 43 of 44 gated cells within ±1%, 0 gaps, 1 owner-accepted exception (ICLR 2013 main, 23 vs 24, decision-016). Its paper check ran against the real record op:iclr:2013:11y_SldoumvZl (ICLR 2013, track workshop, status accepted, Factorized Topic Models), outside the main cell as required. AC#1: each of the 44 gated cells has exactly one row with a URL citation in coverage-sources.md (checked by script against the report). Every report cell count equals a jq tally over records.jsonl; manifest record_count 95,938 equals the line count. Cells within ±1% but not equal: ICLR 2018 +1, 2019 +1, 2021 −1, 2022 −1, 2023 −1, 2024 +1, 2025 +3; ICML 2025 −3 (fact sheet 3,260 vs PMLR/OpenReview 3,257); NeurIPS 2021 main +1. No stale causes or exceptions. The stale 'unexplained; TASK-054 resolves' notes on NeurIPS 2021 (TASK-125) and 2024 (TASK-072) in coverage-sources.md, the coverage-reporting and neurips-proceedings skills and the facts doc now name what explained them.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
op eval coverage (eval/coverage_report.py) renders docs/results/<date>-coverage.md from api.coverage.compute's data for an index: every venue × year × track cell with indexed accepted, official, Δ, Δ%, gate, missing abstracts, unknown track/status and statuses indexed; gated official cells with no records as gaps; cause notes and owner-accepted exceptions from docs/results/coverage-causes.toml (spec 07 §C as amended, decision-016); listings that skipped entries and OpenReview crawls needing attention; --check. First real report (docs/results/2026-09-29-coverage.md, snapshot 4cd2bba17cad…, index b170674bcf49): M4 gate PASS, 43 of 44 gated cells within ±1% and ICLR 2013 main an owner-accepted exception verified against op:iclr:2013:11y_SldoumvZl; coverage-sources.md cites one official count for each of the 44 gated cells.
<!-- SECTION:FINAL_SUMMARY:END -->
