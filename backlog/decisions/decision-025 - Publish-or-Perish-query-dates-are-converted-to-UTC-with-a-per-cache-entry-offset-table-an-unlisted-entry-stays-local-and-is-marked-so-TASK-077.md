---
id: decision-025
title: >-
  Publish or Perish query dates are converted to UTC with a per-cache-entry
  offset table; an unlisted entry stays local and is marked so (TASK-077)
date: '2026-10-01 15:10'
status: accepted
---
## Context

The RIS importer (spec 01, `ingest/ris.py`) takes each record's `fetched_at` from Publish or Perish's
`M1  - Query date: YYYY-MM-DD HH:MM:SS`. PoP writes that line in the local wall time of the machine that ran
the search, with no zone. Until now it was stored labelled UTC because the offset wasn't recorded. A search run
near midnight could then be dated a day off, and PRISMA-S keeps search dates and crawl dates apart. The M2
gate (review-methodologist) raised this, and TASK-077 asked for the offset to be recorded and the dates
converted, or for the dates to be marked local.

Evidence for the offset: PoP keeps its own record of each query, with the run time in Unix epoch seconds,
which carry no zone. For each of the two Trust-Evals searches, one of those times matches a RIS query date to
the second:
- the 2025–26 search (cache entry `out-covidence`): epoch 1789826585 is 2026-09-19T14:03:05Z, and the RIS
  reads `Query date: 2026-09-19 10:03:05`;
- the 2020–24 search (cache entry `out-covidence-2020-2024`): epoch 1790180170 is 2026-09-23T16:16:10Z, and the
  RIS reads `Query date: 2026-09-23 12:16:10`.

Both give UTC−04:00 (Eastern daylight time). Only these two timestamps are taken from PoP's data.

Options considered:
1. **Mark only.** Keep the wall times, and mark every RIS window "local, offset unknown". This is small and
   changes no snapshot bytes, but it leaves a known offset unused and the dates still uncertain.
2. **Convert with a recorded offset** (chosen). Record the offset per cache entry in a committed table, and
   convert at import. An entry with no row keeps option 1's behaviour, explicitly marked.
3. **An `op ingest ris --utc-offset` option, stored in the cache entry.** The existing cache entries are
   immutable, and a re-ingest under the same name with different files is refused. Recording the offset would
   mean re-ingesting under new names, and snapshot replay would depend on a file that lives only in `data/`.

## Decision

We convert Publish or Perish query dates to UTC with the offset recorded per cache entry in
`backend/src/openproceedings/ingest/ris_offsets.toml` (each row's evidence beside it). An entry missing from
that table keeps its local wall time, labelled UTC, and is marked "local, offset unknown". The project owner
decided this on 2026-10-01: PoP's epoch records are accepted as evidence, the dates are converted, and both
searches are at −04:00.

## Consequences

- `ImportReport.utc_offset` (the offset used, or null) is written into each RIS report in the snapshot
  manifest. A new manifest key, `query_dates: {"ris": "utc" | "local"}`, says whether the RIS window was
  converted: `utc` only when every RIS report has an offset. The key is additive, like the takedown keys, so
  there is no format bump. A manifest without it (built before TASK-077) reads as `local`, which is what it
  holds.
- `crawl_dates_kind` (an open set, decision-009) gains `scholar_query_dates_utc` and `mixed_utc`.
  `scholar_query_dates` and `mixed` keep their meaning (local time), so a search record saved before this
  change still reads correctly. The record page, the methods text and the CLI say "(local time)" only for the
  local kinds. Specs 01, 04 and 05, the copy deck (RC-9) and the `prisma-reporting`, `search-records`,
  `snapshots` and `ris-format` skills say so.
- **Reproducibility.** `fetched_at` is not in `content_hash`, but it is in `records.jsonl`, so rebuilding the
  snapshot from the same cache gives a new `snapshot_hash`, and with it a new `index_version`. Every RIS
  claim's `fetched_at` moves 4 hours later; no date changes:
  - 2025–26 search: 00:54–10:03 local becomes 04:54–14:03Z;
  - 2020–24 search: 12:02–12:16 local becomes 16:02–16:16Z.

  After the rebuild, existing search records replay as `drifted`, with `snapshot_hash` named as the changed
  input, because their provenance times changed, not their papers: the re-run finds the same papers
  (membership-identical, `+0 / −0`). There is no public instance yet, so no published record is affected.
  Old snapshots stay as they are (immutable).
- The rebuild is left to the owner, as a step after this merges (`op snapshot build`, then the index build).
  This change alters no file under `data/`.
- A future PoP search needs a row in `ris_offsets.toml` before its snapshot, with its own evidence, or its
  window reads as local. Revisit this if PoP starts writing a zone in the query date, or if a search's offset
  can't be found: that search then stays marked local, and nothing is guessed.

