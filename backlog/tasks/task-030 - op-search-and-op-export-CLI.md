---
id: TASK-030
title: op search and op export CLI
status: In Progress
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-09-26 21:55'
labels:
  - engine
  - api
milestone: m-2
dependencies:
  - TASK-025
  - TASK-026
  - TASK-027
ordinal: 29000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Spec 08 §CLI.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 op search supports --mode scholar, --explain, --engine tantivy|reference, --ids
- [x] #2 op export --format ris|csv|bibtex|jsonl streams the full set ordered by id
- [x] #3 The Trust-Evals Most Updated string runs end to end on the M2 snapshot
- [x] #4 CLI prints diagnostics to stderr as user output (not logging); at most one search_run INFO line with the same privacy-safe fields as the API access log
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented. op search: ranked hits by default (total, default-filter exclusions via engine/exclusions.py, canonical, then rank/score/id/venue/year/title for --limit with --sort); --ids; --explain; --engine reference runs the oracle over the index's snapshot, --ids only (it has no ranking or compiled query). op export "<q>" --format ris|csv|bibtex|jsonl [--mode] [--index] [--out]: streams TantivyEngine.documents (every match's display record, id order, one document at a time) through export.py; --out is written beside the target and renamed (no partial file on failure); the count written must equal the query's total (EngineInternalError otherwise). Diagnostics go to stderr as user output; one search_run INFO line (command, mode, engine, index_version, canonical_hash, total, ms; never the query). export.py (shared with task-036): RIS TY CPAPER/TI/AB/AU/PY/T2/UR forum,pdf,proceedings/DO/ID/KW track/N1 provenance, line breaks collapsed; CSV with BOM, spec 01 fields + index_version + canonical_hash; BibTeX @inproceedings, <lastname><year><firstword> keys with a/b suffixes, braces escaped only when unbalanced, note provenance, openproceedings_id; JSONL. refaudit==0.4.9 pinned as a dev dependency (spec 04). Tests (test_export.py): each format round-trips its ids in id order; BibTeX parses with refaudit; CSV BOM/columns; the CLI's export file, failure without a partial, stdout, ranked output, oracle == Tantivy through the CLI, --engine reference refused without --ids, one search_run line without query text. AC3 (local, real corpus): main-7-most-updated in Scholar mode gives 21 records; all four formats exported 21; refaudit parsed 21 BibTeX entries with 21 ids; --engine reference --ids equals Tantivy's. Also carries task-029's CLI review fix (verify the index before reading its manifest; one _index_path for search, export and parity).
<!-- SECTION:NOTES:END -->
