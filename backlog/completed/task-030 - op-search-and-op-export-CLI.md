---
id: TASK-030
title: op search and op export CLI
status: Done
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-09-26 22:33'
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

Review fixes (all ACs confirmed; 21/21 locally). Musts: BibTeX keys come from a set of every key issued, so a suffixed key (smith2024deepa) never meets a real one (the real one takes smith2024deepaa); values keep braces only when balanced with none escaped, otherwise drop them (BibTeX counts braces raw, other parsers honour \\{, and a misread entry swallowed the next), escape & % #, and never end on a backslash. Shoulds: --out goes to a mkstemp file beside the target, counted against the total before the rename (a short export leaves the user's file untouched and no temp file); BrokenPipeError exits 0 quietly with stdout sent to devnull; ranked output takes one collection via TantivyEngine.page (ids with scores; search() uses it) instead of re-ranking the whole set; spec 04 says which spec 01 fields CSV leaves out (provenance, content_hash: in the snapshot index_version pins); CSV text cells starting = + - @ tab CR get a ' prefix (OWASP); a parse error logs cli_refused at DEBUG and an InternalError at ERROR; --engine reference verifies the index and refuses a same-named snapshot with another hash; tests now cover CSV keywords/doi, BibTeX url, the count check, the formula guard, a closed pipe, --out as a directory, and the snapshot mismatch. Nits: temp file via mkstemp (no clobbering X.partial; concurrent exports don't collide); documents() sorts by the ord column and returns (total, stream), so an export collects the match set once; RIS ends 'ER  - ' with its space. Rejected: refaudit reads a title containing '@inproceedings{' as a new entry, a quirk of that parser (real BibTeX reads it inside the braced value), and no such title exists.

Verification (both musts confirmed fixed: 17 edge records read identically by refaudit, pybtex and bibtexparser; BrokenPipe exits 0 silently on a real pipe in every format; page() == search() == ranked() over 117 comparisons; Most Updated 21 in all formats) fixes: --out files get the mode a shell redirect would (the existing file's, else 0666 less the umask) instead of mkstemp's 0600; tests now kill the surviving mutants (a balanced-but-escaped brace title, a swapped } { title, the stdout count check, InternalError logged at ERROR); a missing --out directory is named instead of the temp file; &, %, # and escaped braces are judged by backslash parity (\\\\& gets its & escaped, \\\\{B} keeps its braces); spec 04 calls JSONL the lossless format.
<!-- SECTION:NOTES:END -->
