---
name: prisma-reporting
description: How openproceedings output maps onto a PRISMA 2020 flow diagram and PRISMA-S search reporting — records identified, records removed before screening by automation (the track/status default-filter exclusions), duplicates, records screened — plus the methods-text template from spec 05 and the fields a search record must hold so a methods section can cite it. Use when building or reviewing search records, the exclusion banner, exports' N1 provenance, the "Copy methods text" feature, or any report a systematic review will cite.
---

# PRISMA reporting

## The mapping (PRISMA 2020 flow, "Identification" box)
| PRISMA box | openproceedings value | Source |
|---|---|---|
| Records identified from databases (n) | `total + Σ excluded` = matched set with default filters removed | 03 §Exclusion accounting |
| Records removed before screening: *marked as ineligible by automation tools* (n) | `Σ excluded`, itemized: `track: workshop 212, competition 4`; `status: rejected 88` | `SearchResponse.excluded` |
| Records removed before screening: duplicates (n) | 0 within openproceedings (dedup happens at ingest, 01 §Pipeline); cross-database duplicates are removed later in Covidence | — |
| Records screened (n) | `total` (what the export contains, `X-Total`) | 04 §Exports |

Name the database as "openproceedings (index `<index_version>`)", not as "OpenReview": the index is the
thing searched.

**Only the default filters count as automation exclusions.** Filters the user wrote on purpose
(`year:2020..2026`, `venue:ICLR`) are *search limits*, reported in the search string and the limits line,
not in the "removed" box. Verify at implementation time that `excluded` is computed against the query
without the defaults only, so user limits never inflate it.

**Overlap:** a paper that is both `workshop` and `rejected` must be counted once in `Σ excluded`. The
itemized breakdown must sum to the difference; an overlapping paper goes to the first bucket in the fixed
order (track, then status; spec 03), and the tooltip says so. A breakdown that double-counts misreports the flow diagram.

## PRISMA-S items the tool must make reportable
Database name and version (`index_version`, `tokenizer_version`) · the **full search string** as
canonical (defaults explicit) · date searched (UTC) · limits (years, venues, tracks, statuses) · the
number of records · whether the search was re-run (replay status) · a stable link to the search record.

## Search record fields (04 §Search records) — all required
input, canonical, mode, `index_version`, UTC timestamp, `total`, `excluded`, `ids_hash =
sha256(sorted ids)`, plus the translations/expansions shown at the time. Replay status `reproduced` (same
index, same `ids_hash`) or `drifted` (newer index, with `+added / −removed`). A `mismatch` (same index, different `ids_hash`) is a
bug that breaks guarantee 4. Never cite a search record in that state. Never report a drifted
count as the original.

## Methods-text template (spec 05, component 8)
> Searched openproceedings (index `a1b2c3`, 2026-09-25) with `<canonical>`; 412 records; 304 removed
> before screening by track/status filters.

Extended form for the paper (verify wording with the review lead):
> We searched NeurIPS, ICLR and ICML titles and abstracts with openproceedings (index `<v>`, tokenizer
> `<t>`, searched `<date>` UTC; search record `<url>`) using `<canonical>`. The search matched `<N>`
> records; `<E>` were removed before screening by automated track/status filters (`<breakdown>`), leaving
> `<total>` exported to Covidence. Matching is exact-token on title and abstract with no stemming.

## Gotchas
- Wildcard expansions are part of the method: report them (or cite the record, which stores them).
- The export `N1` line (`openproceedings <index_version> · query <canonical_hash> · <UTC date>`) lets a
  screener trace any record back to its search.
- Semantic near-misses (06) are **not** "records identified"; if a review adds any, they are "records
  identified from other methods", reported separately.
