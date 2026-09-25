---
name: prisma-reporting
description: How openproceedings output maps onto a PRISMA 2020 flow diagram and PRISMA-S search reporting — records identified, records removed before screening by automation (the track/status default-filter exclusions), duplicates, records screened — plus the methods-text template from spec 05 and the fields a search record must hold so a methods section can cite it. Use when building or reviewing search records, the exclusion banner, exports' N1 provenance, the "Copy methods text" feature, or any report a systematic review will cite.
---

# PRISMA reporting

## The mapping (PRISMA 2020 flow, "Identification" box)
| PRISMA box | openproceedings value | Source |
|---|---|---|
| Records identified from databases (n) | the count of `identification_query` (the canonical string minus the default conjuncts, 02 §Default filters) = `total + excluded.total` | 03 §Exclusion accounting |
| Records removed before screening: *marked as ineligible by automation tools* (n) | the default-filter buckets except `unknown`, itemized: `track: workshop 212, competition 4`; `status: rejected 88` | `SearchResponse.excluded` |
| Unclassified (`excluded.track.unknown`, `excluded.status.unknown`) | on its **own line**, never folded into "ineligible". Unclassified is not ineligible: the review chooses to report them or screen them | 03 §Exclusion accounting |
| Records removed before screening: duplicates (n) | the ingest dedup counts from the manifest: `dedup.merged` and `dedup.ambiguous_not_merged` (stored in the search record). Cross-database duplicates are removed later in Covidence | 01 §Pipeline, 04 §Search records |
| Records screened (n) | `total` (what the export contains, `X-Total`) | 04 §Exports |

Name the database as "openproceedings (index `<index_version>`)", not as "OpenReview": the index is the
thing searched.

**Only the default filters count as automation exclusions.** Filters the user wrote on purpose
(`year:2020..2026`, `venue:ICLR`) are *search limits*, reported in the search string and the limits line,
not in the "removed" box. Spec 03 decides this: `excluded` is computed against the `identification_query`,
which keeps every user-written filter, so user limits never inflate it. A default is recognised by content,
so a typed conjunct identical to a default counts as the default. "Identified" is therefore conditional on
the user's own limits, and the methods text says so.

**Overlap:** a paper that is both `workshop` and `rejected` must be counted once in `Σ excluded`. The
itemized breakdown must sum to the difference; an overlapping paper goes to the first bucket in the fixed
order (track, then status; spec 03), and the tooltip says so. A breakdown that double-counts misreports the flow diagram.

## PRISMA-S items the tool must make reportable
Database name and version (the **full** `index_version`, `tokenizer_version`, `query_version`) · the
**full search string**: the `identification_query` plus the default clauses · date searched (UTC,
`searched_at`) and, separately, the crawl date (`crawl_dates`) · limits (years, venues, tracks, statuses) ·
the number of records · expansions, translations and warnings · the dedup counts · whether the search was
re-run (replay status) · a stable link to the search record.

## Search record fields (04 §Search records) — all required
The full table is in `.claude/skills/search-records/SKILL.md`: `input`, `mode`, `canonical`,
`canonical_hash`, `identification_query`, `index_version`, `tokenizer_version`, `query_version`,
`snapshot_hash`, `crawl_dates`, `searched_at`, `total`, `excluded` (with `unknown` itemised), `expansions`,
`translations`, `warnings`, `ids` and `ids_hash`, `dedup`, and `semantic_version` if the near-miss panel was
open. Replay status (HTTP 200): `reproduced` (same `index_version` and `query_version`, `ids_hash` and
`excluded` match); `drifted` (only a different index or query version available, with the changed inputs
named and `+added / −removed`; `+0 / −0` is "membership-identical"); `mismatch` (same versions, but
`ids_hash` or `excluded` differ) is a bug that breaks guarantee 4. **Do not cite** a record in `mismatch`:
the record page shows "do not cite" with no methods text and no export. Never report a drifted count as the
original.

## Methods-text template (spec 05 §Save search record)
The text says **which string reproduces which number**, gives the **full** `index_version` (never a
prefix), and keeps the search date separate from the crawl date:
> We searched openproceedings on 2026-09-25 (index `a1b2c3d4e5f6`, built from a crawl of 2026-09-20) with
> the string `<identification_query>`, which identified 716 records. Default filters `track:(main OR
> datasets_benchmarks OR position)` and `status:accepted` removed 304 of them before screening (212
> workshop, 4 competition, 88 rejected); 0 were unclassified. 412 records were screened. Search record:
> <url>.

Not generated for a `mismatch` record.

## Gotchas
- Wildcard expansions are part of the method: report them (or cite the record, which stores them).
- The export `N1` line (`openproceedings <index_version> · query <canonical_hash> · <UTC date>`) lets a
  screener trace any record back to its search.
- Semantic near-misses (06 §Features item 5): papers found by *revising `q`* from a near-miss chip are
  database records from the revised string. The revision belongs in the search-development narrative, not
  under "other methods". Only a paper added **outside** `q` counts as "records identified from other
  methods". Search records store `semantic_version` whenever the panel was open.
