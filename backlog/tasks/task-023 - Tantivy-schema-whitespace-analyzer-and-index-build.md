---
id: TASK-023
title: 'Tantivy schema, whitespace analyzer and index build'
status: In Progress
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-09-26 19:07'
labels:
  - engine
milestone: m-2
dependencies:
  - TASK-010
  - TASK-022
  - TASK-071
ordinal: 22000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Spec 03 §Index schema, §Tokenizer, §Versioning (tantivy-indexing, index-versioning skills).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Index fed pre-normalized text; analyzer only splits on whitespace
- [x] #2 index_version = sha256(snapshot_hash, TOKENIZER_VERSION, SCHEMA_VERSION, ranking params)[:12]
- [x] #3 data/indexes/<v>/ immutable; op index build < 2 min on the M4 corpus (bench)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented in backend/src/openproceedings/engine/index.py (+ storage.py, the lock/stage/sync helpers now shared with snapshots) and op index build. tantivy==0.26.2 pinned. exact_v1 = whitespace tokenizer, no filters; every field's tokens checked through it; tokens over 65,530 bytes (Tantivy's silent drop, measured) refuse the build. index_version over canonical JSON, pinned by a test (0*64, v2, schema 1 -> 6208c84b36b6). Index files read-only and hashed in the manifest; verify_index re-hashes; an existing version is verified, never rebuilt. Bench (local, 8 cores, 80k synthetic records from the real text): 32.9 s, 187 MB (129.9 s before parallel normalize); real corpus 1805 docs in 3 s. The directory stays writable (Tantivy readers need their lock file).

Review round (2026-09-26): record is a stored bytes field (a JSON field was indexed by default: guarantee 2); verify_index recomputes the id from the manifest's inputs; existing indexes re-sealed; records stream in chunks (peak 355 MB at 80k, was 2 GB; 33 s; 45 MB index); pool starts lazily; a dead worker is a one-line refusal; ranking numbers canonicalized as floats; hash-prefix lookup skips .tmp- dirs; rows for every surviving mutant. Read-back parity is task-029; read-only mounts noted on task-065; raw id/facet length check rejected as unreachable (PaperRecord bounds them).
<!-- SECTION:NOTES:END -->
