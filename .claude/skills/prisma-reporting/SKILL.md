---
name: prisma-reporting
description: How openproceedings output maps onto a PRISMA 2020 flow diagram and PRISMA-S search reporting — records identified, records removed before screening by automation (the track/status default-filter exclusions), duplicates, records screened — plus the methods-text template from spec 05 and the fields a search record must hold so a methods section can cite it. Use when building or reviewing search records, the exclusion banner, exports' N1 provenance, the "Copy methods text" feature, or any report a systematic review will cite.
---

# PRISMA reporting

## The mapping (PRISMA 2020 flow, "Identification" box)
| PRISMA box | openproceedings value | Source |
|---|---|---|
| Records identified from databases (n) | the count of `identification_ast`, the set `identification_query` names (the canonical query minus the default conjuncts, 02 §Default filters; never re-parsed, since the string can be `""` or all-negative) = `total + excluded.total` | 03 §Exclusion accounting |
| Records removed before screening: *marked as ineligible by automation tools* (n) | the default-filter buckets except `unknown`, itemized: `track: workshop 212, competition 4`; `status: rejected 88` | `SearchResponse.excluded` |
| Records removed before screening: *removed for other reasons* (n) — unclassified (`excluded.track.unknown`, `excluded.status.unknown`) | its **own count**, labelled apart from "ineligible" and never folded into it (`op search` prints both on the "removed by default filters" line, each named). Unclassified is not ineligible: the review chooses to report them or screen them | 03 §Exclusion accounting |
| Records removed before screening: duplicates (n) | **0 at this stage** — cross-source duplicates were merged at ingest, before indexing (01 §Pipeline). Duplicates against other databases are removed later in Covidence | 01 §Pipeline |
| Records screened (n) | `total` (what the export contains, `X-Total`) | 04 §Exports |

Name the database as "openproceedings (index `<index_version>`)", not as "OpenReview": the index is the
thing searched.

**Only the default filters count as automation exclusions.** Filters the user wrote on purpose
(`year:2020..2026`, `venue:ICLR`) are *search limits*, reported in the search string and the limits line,
not in the "removed" box. Spec 03 decides this: `excluded` is computed against `identification_ast` (the set
`identification_query` names), which keeps every user-written filter, so user limits never inflate it. A default is recognised by content,
so a typed conjunct identical to a default counts as the default. "Identified" is therefore conditional on
the user's own limits, and the methods text says so.

**Overlap:** a paper that is both `workshop` and `rejected` must be counted once in `Σ excluded`. The
itemized breakdown must sum to the difference; an overlapping paper goes to the first bucket in the fixed
order (track, then status; spec 03), and the tooltip says so. A breakdown that double-counts misreports the flow diagram.

## PRISMA-S items the tool must make reportable
Database name and version (the **full** `index_version`, `tokenizer_version`, `query_version`) (a
review of non-English titles also states the tokenizer's known limits, spec 02 §Known limits: CJK runs
are one token; Latin/Greek/Cyrillic accents and Hebrew/Arabic vowel points fold) · the
**full search string**: the `identification_query` plus the default clauses · date searched (UTC,
`searched_at`) and, separately, the corpus-wide summary window (`crawl_dates["*"]`, cited from–to: "a
crawl run 2026-09-18 to 2026-09-20"; per-source windows remain in the record for audit) · limits (years, venues, tracks, statuses) ·
the number of records · expansions, translations and warnings · the deduplication process (item 16) ·
whether the search was re-run (replay status) · a stable link to the search record.

**Deduplication (PRISMA-S item 16) is a process statement, not a removal count.** The corpus-wide
`dedup.merged` and `dedup.ambiguous_not_merged` counts from the manifest (stored in the search record's
`dedup`, 04 §Search records) describe how the database was built: cross-source records merged at ingest,
before indexing. `dedup.track_not_merged` and `dedup.venue_year_not_merged` (body v2) count look-alike
pairs deliberately kept apart (a pair the dedup track rule refuses; two records of one venue-year); the
statement may mention them. Report them only in that statement. Never put them in the flow diagram's
duplicates box or present them as removed by this search. **Duplicates Covidence finds** (between this export
and other databases' records) **do** go in the flow diagram's duplicates box: they are the review's own
deduplication, not openproceedings'.

## Bootstrap corpora are not citable identification numbers
An index built only from bootstrap sources (`vocab.BOOTSTRAP_SOURCES`: the RIS import of an earlier Scholar
search, spec 01) holds that search's output, not a database. Its counts describe that corpus and are **not**
PRISMA "records identified from databases". A search record says so: `sources` (the manifest's source
names) and `identification_citable: false`, from the same `vocab.bootstrap_only` test `op search` uses for
its "note: bootstrap corpus" line. Its window is not a crawl: `crawl_dates_kind["*"]` is
`scholar_query_dates_utc` (Publish or Perish's query dates, converted to UTC with the offset
`ingest/ris_offsets.toml` records, decision-025) or `scholar_query_dates` (an entry with no recorded offset:
local time labelled UTC, so an end can be a day off, worded with "(local time)"), and must be worded "Scholar
searches run <from> to <to>", never "a crawl"; a `mixed` window (real crawls plus a bootstrap source, from M4)
reads "crawls and Scholar searches run <from> to <to> (Scholar dates in local time)", and a `mixed_utc` one
the same without the parenthesis (spec 05 §Save search record). The record page shows the CLI's caution and **no methods
text** when `identification_citable` is false; a v1 record (null: not recorded) shows the caution "not
recorded whether this index is a bootstrap corpus: these counts may not be PRISMA identification numbers"
and no methods text either.

## Search record fields (04 §Search records) — all required
The full table is in `.claude/skills/search-records/SKILL.md`: `input`, `mode`, `canonical`,
`canonical_hash`, `identification_query`, `index_version`, `tokenizer_version`, `query_version`,
`snapshot_hash`, `crawl_dates` (with `crawl_dates_kind`), `sources`, `identification_citable`, `searched_at`,
`total`, `excluded` (with `unknown` itemised), `expansions`, `translations`, `warnings`, `ids` and `ids_hash`,
`dedup`, and `semantic_version` if the near-miss panel was open (phase 2, deferred; always null in v1). Replay status (HTTP 200): `reproduced` (same `index_version` and `query_version`, `ids_hash` and
`excluded` match); `drifted` (only a different index or query version available, with the changed inputs
named and `+added / −removed`; `+0 / −0` is "membership-identical"); `mismatch` (same versions, but
`ids_hash` or `excluded` differ) is a bug that breaks guarantee 4. **Do not cite** a record in `mismatch`:
the record page shows "do not cite" with no methods text and no export. Never report a drifted count as the
original.

## Methods-text template (spec 05 §Save search record)
The text says **which string reproduces which number**, gives the **full** `index_version` (never a
prefix), and keeps the search date separate from the crawl date:
> We searched openproceedings on 2026-09-25 (index `a1b2c3d4e5f6`, built from a crawl run 2026-09-18 to
> 2026-09-20) with
> the string `<identification_query>`, which identified 716 records within the limits it states
> (`year:2020..2026`). Default filters `track:(main OR datasets_benchmarks OR position)` and
> `status:accepted` removed 304 of them before screening (212 workshop, 4 competition, 88 rejected); that
> count includes 0 unclassified records (track or status unknown), itemised separately. Cross-source
> duplicates were merged at ingest, before indexing (merge counts are in the search record). Database scope: coverage
> report for snapshot `<snapshot_hash>`. 412 records were screened. Search record: <url>.

**When `identification_query` can't be cited as a search** (spec 02 §Default filters, as built): if it is
`""` (the query was nothing but defaults) the text says "all indexed records"; if
it is all-negative (the only positive clause was a default, e.g. `NOT track:workshop`) the text cites
`canonical` as the string searched and describes the identified set as "`canonical` without its default
filters". Counts always come from `identification_ast`, never from re-parsing the string.

**Scholar-mode strings** (spec 05 §Save search record): the methods text cites the input as typed, states
that it was translated, and names the translations: `source:` → `venue:`, decision-002's phrase reading
of `|` items (unlike Google Scholar), `$` as the WoS zero-or-one wildcard, and the no-stemming terms
(`COMPAT_NO_STEMMING`). PRISMA-S asks for search strategies "exactly as run"; the record stores both.

- **Unclassified** records are inside the removed count, and itemised in it.
- The **limits clause** names every filter the user wrote (`year:`, `venue:`, a non-default `track:` set):
  "identified" is conditional on them (03 §Exclusion accounting). With none it reads "with no limits".
- The **coverage report**, cited with its snapshot hash, is the database-scope caveat (07 §C).
- A review may instead report the default filters as limits, citing the canonical string; the record
  stores both strings, so either framing can be cited.

Not generated for a `mismatch` record, nor for one whose `identification_citable` is not true. The crawl
clause is `crawl_dates["*"]` from–to, both dates (a crawl spans days; spec 04), never one date.

## Gotchas
- Wildcard expansions are part of the method: report them (or cite the record, which stores them).
- The export `N1` line (`openproceedings <index_version> · query <canonical_hash> · exported <UTC date>`,
  plus ` · record <record_id> · searched <UTC date>` when exported from a search record) lets a screener
  trace any record back to its search.
- Semantic near-misses (06 §Features item 5; phase 2, deferred by decision-017): papers found by *revising `q`* from a near-miss chip are
  database records from the revised string. The revision belongs in the search-development narrative, not
  under "other methods". Only a paper added **outside** `q` counts as "records identified from other
  methods". Search records store `semantic_version` whenever the panel was open.
- **Withheld abstracts** (decision-021, decision-022). An export can hand over records without their abstract:
  every one when the exported index's snapshot can't be verified (`X-Abstract-Source: unavailable`, EX-E8),
  or the ones a rights holder had removed (a takedown: `X-Abstracts-Withheld: <n>`, EX-E9; each record's RIS
  `N1` / BibTeX `abstract_withheld` says so, CSV/JSONL `abstract_withheld_reason`; `op export` says the number
  on stderr). Covidence shows screeners
  no `N1`, so report those records as screened on title and metadata alone, with their number. A search
  record's ids never change for a takedown (its pinned index still matches the withheld text, decision-022),
  but what an export of it contains can: cite the export date (the provenance `N1` carries it). The coverage
  report's missing-abstract count leaves withheld ones out and names them under its totals.
