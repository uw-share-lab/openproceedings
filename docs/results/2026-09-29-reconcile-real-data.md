# Reconcile on the real crawl: 6 OpenReview acceptances made `unknown`, 5 listed under another title (TASK-072), 2026-09-29

**Result:** on snapshot `2026-09-29-eb72536c21d1` (index `b2a358e2f955`), decision-005's reconcile step
made **6** OpenReview-accepted records `unknown`. It judged 29 crawled (proceedings source, venue, year) sets of listings, left
0 alone as incomplete, and left **1** record alone because it shares a title with a listing it didn't merge
with (NeurIPS 2021 main). Every changed cell then equals its official count. The M4 gate stays FAIL at 43 of 44
(ICLR 2013 main, which reconcile doesn't touch). Only 1 of the 6 is really absent from the proceedings
(NeurIPS 2024 `ftqjwZQz10`, DEX). The other 5 are listed under another title. 3 were renamed for the
camera-ready, and 2 have titles mangled by `html.py` dropping a charref's `;` (TASK-128). These numbers are
refreshed after TASK-128 lands.

## What was run
The cache is the TASK-126 scratch cache (the main checkout's `data/cache`: RIS, OpenReview v1/v2, ICLR archive,
NeurIPS proceedings, PMLR). `<scratch>` is a throwaway directory.
```
uv run --locked op snapshot build --from <cache> --out <scratch>/snapshots
uv run --locked op index build --snapshot <scratch>/snapshots/2026-09-29-eb72536c21d1 --out <scratch>/indexes
uv run --locked op eval coverage --index b2a358e2f955 --date 2026-09-29 --out <scratch>/report
```
The build logs `proceedings_reconciled` with `crawls: 29, unlisted: 6, shares_listing: 1, incomplete: 0`.
`op snapshot diff` against the same build without reconcile gives 6 changed records (status only) and an
identical `merges.csv`. `dedup` run again on the new records is a fixed point.

## Cells changed (indexed accepted, before → after; official from `coverage-sources.md`)
| venue | year | track | before | after | official |
|---|---|---|---|---|---|
| NeurIPS | 2023 | main | 3,219 | 3,218 | 3,218 |
| NeurIPS | 2023 | datasets_benchmarks | 324 | 322 | 322 |
| NeurIPS | 2024 | main | 4,035 | 4,034 | 4,034 |
| NeurIPS | 2025 | main | 5,287 | 5,286 | 5,286 |
| NeurIPS | 2025 | datasets_benchmarks | 498 | 497 | 497 |

Each of those cells was one over per affected paper because the paper counted twice: once as the OpenReview
note and once as the unmerged listing.

## Decision-005's track row, measured and not enforced (TASK-130)
There are **151** records whose track comes from a proceedings listing with no OpenReview claim, in a venue-year
that `statuses.on_openreview` says is on OpenReview. This was counted over `records.jsonl` with a one-off
script: records with a proceedings source and no OpenReview source.
- ICLR 2014: 1 (an accepted archive paper whose OpenReview note didn't merge).
- ICLR 2016: 80 (OpenReview holds only ICLR 2016's workshop track).
- NeurIPS 2021–2025 main and D&B: 6 (the listings paired with the rows above, plus the one sharing a title).
- NeurIPS 2025: 64 `other` (Creative AI).

Giving those records track `unknown` would move ICLR 2016 main from 80 to 0 and ICLR 2014 main from 35 to 34
(−2.9%, outside the gate's ±1%). The row was left for the review lead to decide (TASK-130).

## After the review (stated count and `see_also` required)
The review made a listing count as complete only when it states a count and names no unfollowed volume. On
this crawl, every listing names no unfollowed volume. One listing states no count: NeurIPS 2021 D&B
(`datasets-benchmarks-proceedings.neurips.cc/paper/2021`, listed 174, records 174, official 174). So NeurIPS 2021
is no longer judged. It made 0 records `unknown` before, so no status changes. The log line moves to
`crawls: 29, unlisted: 6, shares_listing: 0, incomplete: 1`.

The review also dated each absence claim by its own listing's index-page fetch, not the crawl's last fetch. The
rebuild from the same cache is `2026-09-29-7fd4c937496e`. Against `eb72536c21d1` it has the same 95,940 ids and
byte-identical `merges.csv` and `conflicts.csv`. It differs only in the 6 absence claims' `fetched_at`, for
example NeurIPS 2024's claim moves from 14:21:59Z (the last paper page) to 05:26:34Z (the index page).
