---
id: TASK-022
title: Snapshot build and diff with manifest
status: In Progress
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-09-26 17:10'
labels:
  - ingest
milestone: m-2
dependencies:
  - TASK-019
  - TASK-020
  - TASK-021
ordinal: 21000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Spec 01 §Pipeline step 5 (snapshots skill).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 records.jsonl sorted by id; manifest with counts, sources, crawl dates, dedup counts, snapshot_hash
- [x] #2 Same inputs → byte-identical output (determinism test)
- [x] #3 op snapshot diff reports added/removed/changed records
- [x] #4 op snapshot build takes the RIS inputs (spec 01's op ingest ris <mended.ris>...; resolved.json beside each) and writes each file's ImportReport (read, imported, skipped by reason, abstract_missing, status) into the manifest
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented in backend/src/openproceedings/ingest/snapshot.py and cli.py: op ingest ris (checks each scholarmend output imports, caches it with its resolved.json under <data-dir>/cache/ris/<dir name>/, identical re-ingest is a no-op, different files under a cached name refused); op snapshot build (import cache -> dedup -> records.jsonl / manifest.json / merges.csv / conflicts.csv in <crawl date>-<shorthash>, temp dir + os.replace, existing hash reported not rebuilt, occupied target refused); op snapshot diff (added / removed / changed with hashed fields named, display-only and provenance-only counts). Determinism test builds twice (different built_at) and compares bytes. Real corpus, local only (2026-09-26): data/snapshots/2026-09-23-d5ab3d6d444a, 1805 records, no merges or conflicts; rebuild reports it (created false).

Review round (2026-09-26): all-or-nothing cache writes of the exact checked bytes; .tmp-/hidden entries never sources and swept; fsync + rename + read-only; an existing target re-hashed, never trusted; load_records needs a matching manifest, unique ids, and errors without record text; diff adds rekeyed; manifest gains format/record-schema/tokenizer/openproceedings versions, crawl_window and CSV hashes; ImportReport's scholarmend_version is now parser_version; CLI: OSError refusals, cli_refused log line, full command names, --data-dir defaults to OP_DATA_DIR or the repo's data/, unknown options before a stub rejected.
<!-- SECTION:NOTES:END -->
