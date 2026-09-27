---
id: TASK-022
title: Snapshot build and diff with manifest
status: Done
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-09-26 18:34'
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

Verification round (2026-09-26): exclusive flock per written directory (concurrent builds/ingests take turns; sweeps only under the lock); a placed snapshot is checked before it is reported; an existing target must be complete and current-format (else refused with retire advice) and is re-locked; case/Unicode-folded cache name clashes refused; symlinked inputs read from their target; reports name the cache entry; resolved.json shape-checked; stub arguments must follow the stub's name; F_FULLFSYNC on macOS. The local pre-fix snapshot data/snapshots/2026-09-23-d5ab3d6d444a (old manifest format) must be retired by hand and rebuilt.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Snapshots and the op CLI (ingest/snapshot.py, cli.py): op ingest ris caches scholarmend outputs all-or-nothing; op snapshot build writes a deterministic, crash-safe, locked, read-only snapshot with a versioned manifest; op snapshot diff reports added/removed/rekeyed/changed/display-only/provenance-only. Verified: 50+ tests (determinism, immutability, concurrency, refusals without record text, CLI end to end), two review rounds with mutation passes, and a real build of the Trust-Evals corpus (1805 records, reproducible).
<!-- SECTION:FINAL_SUMMARY:END -->
