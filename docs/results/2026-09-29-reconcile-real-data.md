# Reconcile on the real crawl: 4 OpenReview acceptances made `unknown`, 3 listed under another title (TASK-072), 2026-09-29

**Result:** on snapshot `2026-09-29-4cd2bba17cad` (index `b170674bcf49`), decision-005's reconcile step
made **4** OpenReview-accepted records `unknown`. This build includes TASK-128's `html.py` charref fix. There
were 29 crawled (proceedings source, venue, year) sets of listings. Reconcile left 1 alone as incomplete:
NeurIPS 2021, whose D&B page states no count (see below). Every changed cell then equals its official count.
The M4 gate **passes**: 43 of 44 gated cells are within ±1%, and ICLR 2013 main is the owner-accepted exception
(decision-016), which reconcile doesn't touch. Only 1 of the 4 records is really absent from the proceedings:
NeurIPS 2024 `ftqjwZQz10`, DEX. The other 3 were renamed for the camera-ready, and their listings stay
separate records.

| record | cell | the listing it pairs with |
|---|---|---|
| `op:neurips:2023:3sRR2u72oQ` | NeurIPS 2023 D&B | INSPECT, renamed |
| `op:neurips:2023:pTSNoBTk8E` | NeurIPS 2023 D&B | DynaDojo, renamed |
| `op:neurips:2024:ftqjwZQz10` | NeurIPS 2024 main | none: DEX is on neither the 2024 nor the 2025 listing |
| `op:neurips:2025:mORzRZaqT4` | NeurIPS 2025 D&B | GuardSet-X, listed as PolyGuard |

## What was run
The cache is the TASK-126 scratch cache: the main checkout's `data/cache`, read-only, holding RIS, OpenReview
v1/v2, ICLR archive, NeurIPS proceedings and PMLR. `<scratch>` is a throwaway data directory.
```
uv run --locked op snapshot build --from <cache> --out <scratch>/snapshots
uv run --locked op index build --snapshot <scratch>/snapshots/2026-09-29-4cd2bba17cad --out <scratch>/indexes
OP_DATA_DIR=<scratch> uv run --locked op eval coverage --index b170674bcf49 --date 2026-09-29 --out <scratch>/report
```
The build logs two lines. `proceedings_reconciled` has `crawls: 29, unlisted: 4, shares_listing: 0,
incomplete: 1`. `proceedings_reconcile_skipped` has `crawls: ["neurips_proceedings:NeurIPS:2021"]`.

## Cells changed (indexed accepted, before → after; official from `coverage-sources.md`)
| venue | year | track | before | after | official |
|---|---|---|---|---|---|
| NeurIPS | 2023 | datasets_benchmarks | 324 | 322 | 322 |
| NeurIPS | 2024 | main | 4,035 | 4,034 | 4,034 |
| NeurIPS | 2025 | datasets_benchmarks | 498 | 497 | 497 |

Each of those cells was one over per affected paper, because the paper counted twice: once as the OpenReview
note and once as the unmerged listing.

## NeurIPS 2021 is not judged
A listing counts as complete only when it states a count, matches it, turns every entry into a record, and
names no volume left uncrawled. One listing states no count: NeurIPS 2021 D&B
(`datasets-benchmarks-proceedings.neurips.cc/paper/2021`). It lists 174 entries, 174 became records, and the
official count is 174. It is complete, but the page doesn't say so, so NeurIPS 2021 stays as dedup left it.
Kept deliberately (the conservative rule). On this crawl it would have changed nothing either way: its one
candidate, in 2021 main, shares a title with a listing and would keep its status.

## Decision-005's track row, measured and not enforced (TASK-130)
**149** records get their track from a proceedings listing with no OpenReview claim, in a venue-year that
`statuses.on_openreview` says is on OpenReview. This was counted over `records.jsonl`: records with a proceedings
source (absence claims aside) and no OpenReview source.
- ICLR 2014: 1 (an accepted archive paper whose OpenReview note didn't merge).
- ICLR 2016: 80 (OpenReview holds only ICLR 2016's workshop track).
- NeurIPS main and D&B: 4. Three are the renamed listings above: INSPECT and DynaDojo (2023 D&B) and PolyGuard
  (2025 D&B). The fourth is the 2021 main listing that shares its title with two OpenReview notes.
- NeurIPS 2025: 64 `other` (Creative AI).

Giving those records track `unknown` would move ICLR 2016 main from 80 to 0 and ICLR 2014 main from 35 to 34
(−2.9%, outside the gate's ±1%). The row is left for the review lead to decide (TASK-130).

## Track, decided per track (TASK-130, 2026-09-29)
The owner decided that "on OpenReview" means the venue-year's *track*: the proceedings decide a paper's track
wherever OpenReview doesn't hold that venue-year's track (decision-005). That was already the behaviour: a
record with an OpenReview track claim takes it, and one without takes its listing's. So TASK-130 pins it with
tests and changes no code path. A rebuild from the same cache on the TASK-130 branch
gives the same snapshot, `2026-09-29-4cd2bba17cad` (byte-identical `records.jsonl`, index `b170674bcf49`).
**No cell changes**: 0 of 95,938 records differ in track or status. Every record's track is its OpenReview
claim's where it has one, else its listing's (0 exceptions). The 149 records above keep their
listings' tracks: ICLR 2014 main 1, ICLR 2016 main 80, NeurIPS 2021 main 1, 2023 D&B 2, 2025 D&B 1 and 2025
`other` 64. `op eval coverage` gives **M4 gate: PASS**: 43 of 44 gated cells are within ±1%, and ICLR 2013 main
is the owner-accepted exception (decision-016).

## Before TASK-128 (snapshot `2026-09-29-eb72536c21d1`, index `b2a358e2f955`)
The first check ran before the charref fix. It made **6** records `unknown` and counted **151** track records.
The two extra were NeurIPS 2023 main `Sg3aCpWUQP` and 2025 main `r8UWp9JeJi`. Their listings' titles were
mangled because `html.py` read `&#x27;Ca`/`&#x27;ec` without the `;`, as one hex charref (`'Catch` →
`⟊tch`). So the listings never merged with their notes. After TASK-128 both merge, and their cells (2023 main
3,218, 2025 main 5,286) are exact without reconcile.
