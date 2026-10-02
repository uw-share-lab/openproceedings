---
name: tantivy-indexing
description: The Tantivy index standard for openproceedings — the schema table (field types, positions, stored and fast fields), feeding pre-normalized text through a whitespace-only analyzer so Rust holds no normalization logic, the build procedure from a snapshot, and immutability of data/indexes/<index_version>/. Use when writing or reviewing the index schema, analyzer registration, `op index build`, tantivy-py upgrades, or the tokenizer-parity test.
---

# Tantivy indexing (spec 03 §Tokenizer, §Index schema)

## Schema
| Field | Tantivy type | Indexed | Stored | Fast | Notes |
|---|---|---|---|---|---|
| `id` | text, `raw` tokenizer | ✓ | ✓ | | the stable record id; tie-break key |
| `title` | text, freqs + positions | ✓ | ✓ | | pre-normalized tokens joined by `" "` |
| `abstract` | text, freqs + positions | ✓ | ✓ | | same; a missing abstract is `""`, never omitted |
| `venue`, `track`, `status` | text, `raw` (facet) | ✓ | ✓ | ✓ | one spelling per value, fixed by the ingest vocabulary |
| `year` | u64 | ✓ | ✓ | ✓ | `RangeQuery` target |
| `ord` | u64 | | | ✓ | the record's position in id order; `ids.txt` (hashed with the index) maps it back, so a match set reads as ids without fetching documents |
| `title_rank` | u64 | | | ✓ | the record's position in (casefold(NFKC(display title)), id) order (`title_key`), for `sort=title` |
| `record` | bytes: compact canonical JSON (display title and abstract, authors, urls, presentation, keywords, venue_id_raw) | | ✓ | | **never indexed** (guarantee 2): not a JSON field, which tantivy-py indexes by default; read with `record_of` |

Positions are mandatory on `title`/`abstract` (phrases, NEAR, highlights). Any change to this table bumps
`SCHEMA_VERSION` (`.claude/skills/index-versioning/SKILL.md`).

## Analyzer: `exact_v1`
- The index is fed the output of `query/normalize.py::normalize()` joined by single spaces
  (`.claude/skills/token-contract/SKILL.md`). The registered analyzer **only splits on whitespace**
  (spec 03 §Tokenizer). Never add an ASCII-folding or lower-casing filter: normalized tokens keep letters
  such as `ø`, `ł`, `æ`, `đ` that ASCII folding would change, so the index would match what
  ReferenceEngine doesn't. Keep the Rust side doing **nothing** that `normalize.py` doesn't already do.
- **Never** use the built-in `default` or `en_stem` analyzers. `en_stem` stems. `default` also applies a
  **long-token filter** (verify the current limit in the pinned tantivy version), which drops long tokens
  the oracle keeps, and that is a silent membership difference. Build the analyzer explicitly and check the
  filter list.
- As built (`backend/src/openproceedings/engine/index.py`, tantivy-py **0.26.2**, pinned exactly):
  `TextAnalyzerBuilder(Tokenizer.whitespace()).build()` with no filters, registered with
  `index.register_tokenizer("exact_v1", …)` on every `Index` that is built or opened (`open_index`). The
  whitespace tokenizer splits on ASCII whitespace only, which is enough: normalized tokens never contain
  whitespace. `year` must be added with `Document.add_unsigned` (a Python int goes in as i64 and panics
  the u64 fast field).
- **Token length.** The analyzer keeps any length, but Tantivy's indexer silently drops a token over
  **65,530 UTF-8 bytes** (measured). `build_index` refuses such a record (`MAX_TOKEN_BYTES`) instead of
  losing it; the build also checks every field's tokens through `exact_v1` against `normalize()`.
- Tokenizer-parity test: for every record, the stored text through `exact_v1`, the positions (a phrase
  query per field, read back from the postings) and every term's document frequency (both directions)
  equal `normalize()` output. Run it over the 5k fixture in CI, and over the real corpus locally with
  `op index parity` before promoting an index (decision-004: real text never enters CI). Zero diffs.

## Build procedure (`op index build --snapshot <path | name | snapshot_hash prefix>`)
1. Load the immutable snapshot (`.claude/skills/snapshots/SKILL.md`). Refuse one whose content hash doesn't
   verify.
2. Compute `index_version` **before** building. If `data/indexes/<index_version>/` already exists, verify it
   and stop. Never rebuild in place.
3. Under an exclusive lock on `data/indexes/`, build into a `.tmp-` staging directory. Normalize titles and
   abstracts, streaming the snapshot's records in id order (`iter_records`: one pass that validates each
   line, requires ids strictly ascending and hashes the bytes it reads, refusing at the end if they don't
   match the manifest, so the file checked is the file read) in chunks of 4,096, never all loaded at once.
   `normalize()` is the whole cost, so once a first chunk holds at least 2,000 records a process pool
   shares it (results come back in order); then add documents through a one-thread writer. Commit (only
   after the last record, so a refusal at the end leaves nothing), then wait for merges. A build that fails
   rolls its writer back and waits for its merge threads (dropping Tantivy's lock) before it removes the
   staging directory, since the failing frame's traceback keeps the writer alive and Tantivy could rewrite
   `.tantivy-meta.lock` behind `rmtree`; a directory that still survives is a WARNING
   (`index_build_tmp_left`), and the next build's sweep removes it (`engine/index.py` `_release`).
4. Check the doc count. Write a manifest (`index_version`, snapshot name and hash, `TOKENIZER_VERSION`,
   `SCHEMA_VERSION`, ranking params, tantivy-py version, doc count, build time and ms, and the sha256 of
   every index file).
5. Sync and rename the staging directory to `data/indexes/<index_version>/`, make every file read-only
   except Tantivy's lock files (readers take `.tantivy-meta.lock`, so the directory itself stays
   writable), and verify it: `verify_index` recomputes the id from the manifest's four inputs (it must
   equal the manifest's and the resolved directory's name, so `current` → `<v>` verifies), re-hashes every
   file and re-reads the doc count. A build
   that finds its version already present verifies and re-seals it instead of rebuilding. Opening needs
   write access to `.tantivy-meta.lock` (Tantivy's reader lock), so an index can't be served from a
   read-only mount; the directory itself needn't be writable once the build has left both lock files. The
   compose deployment makes the version directory 0750 with the API's group and only the two lock files
   group-writable (`deploy/index-permissions.sh`; spec 08 §Deploy, TASK-065). Moving `current` is a
   separate release step. `TantivyEngine` opens only a verified index, and refuses (`API_INTERNAL`, "build a
   new index") one whose `schema_version`, `tokenizer_version` or `tantivy_version` differs from the running
   code, or whose bm25 isn't Tantivy's (field-weighted-bm25 skill).

`data/indexes/` is immutable. `protect-data-dir.sh` blocks Write/Edit there, so builds go through the CLI
only.

## Budgets
Build in < 2 min, and an index under 500 MB on disk (spec 03), on the ~80k M4 corpus. Measured by
`backend/tests/bench/report_80k.py` into `docs/results/2026-09-27-bench.md` (synthetic 80k, abstracts of
120-250 words): 30 s, a 99 MB index, 391 MB in the largest single process; the `nightly` workflow's `benchmarks` job
regenerates that report each night into its run summary (TASK-057; the real corpus stays local). An earlier local, undated measurement from the real corpus's text replicated to 81k gave 38.8 s,
140 MB and a 510 MB builder (129.9 s before normalizing in parallel; 2 GB before streaming). Tokenizer parity is read back from the built index
(task-029, `engine/parity.py`, `op index parity`): stored fields through `exact_v1`, positions by a
phrase query per field, and every term's document frequency from the term dictionary
(`terms_with_prefix(field, "")` lists all of it, across segments, deleted documents left out), against
`normalize()` run as the build runs it (`index.normalized`, in parallel).

## Gotchas
- Stored `title`/`abstract` hold normalized text. Keep the original display text in `record` (or the
  snapshot) for results and highlights. Never display the token stream.
- Facet values are case-sensitive in the `raw` tokenizer. `venue:neurips` is case-insensitive in the
  language, so compile maps it to the stored spelling.
- Treat a tantivy-py upgrade as able to change scores or segment behaviour. Re-run determinism and
  differential suites, and always bump `SCHEMA_VERSION`: the engine refuses an index built with another
  Tantivy, and without the bump the new build would get the old `index_version` (`index-versioning`).
