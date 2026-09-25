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
| `record` | JSON (authors, urls, presentation, keywords) | | ✓ | | **never indexed** (guarantee 2) |

Positions are mandatory on `title`/`abstract` (phrases, NEAR, highlights). Any change to this table bumps
`SCHEMA_VERSION` (`.claude/skills/index-versioning/SKILL.md`).

## Analyzer: `exact_v1`
- The index is fed the output of `query/normalize.py::normalize()` joined by single spaces
  (`.claude/skills/token-contract/SKILL.md`). The registered analyzer only splits on whitespace (and
  lower-cases, which is a no-op on normalized input). Spec 03 describes `exact_v1` as split → lower-case →
  ASCII fold. On pre-normalized input these are equivalent. Keep the Rust side doing **nothing** that
  `normalize.py` doesn't already do.
- **Never** use the built-in `default` or `en_stem` analyzers. `en_stem` stems. `default` also applies a
  **long-token filter** (verify the current limit in the pinned tantivy version), which drops long tokens
  the oracle keeps, and that is a silent membership difference. Build the analyzer explicitly and check the
  filter list.
- How a custom analyzer is registered differs between tantivy-py versions. Verify it against the pinned
  version at implementation time, and pin tantivy-py exactly in `pyproject.toml`.
- Tokenizer-parity test: for every record, the tokens Tantivy indexed (read back via the term/position API)
  equal `normalize()` output. Run it over the 5k fixture in CI and the full corpus nightly. Zero diffs.

## Build procedure (`op index build --snapshot <snapshot_hash>`)
1. Load the immutable snapshot (`.claude/skills/snapshots/SKILL.md`). Refuse one whose content hash doesn't
   verify.
2. Compute `index_version` **before** building. If `data/indexes/<index_version>/` already exists, verify it
   and stop. Never rebuild in place.
3. Build into a staging directory on the same filesystem. Add documents in `id` order. Commit, then wait for
   merges.
4. Write a manifest (`index_version`, snapshot hash, `TOKENIZER_VERSION`, `SCHEMA_VERSION`, ranking params,
   tantivy-py version, doc count, build time). Run the parity and doc-count checks.
5. Atomically rename the staging directory to `data/indexes/<index_version>/`. Moving `current` is a
   separate release step.

`data/indexes/` is immutable. `protect-data-dir.sh` blocks Write/Edit there, so builds go through the CLI
only.

## Budgets
Build in < 2 min and < 500 MB on the ~80k M4 corpus (CI bench plus nightly).

## Gotchas
- Stored `title`/`abstract` hold normalized text. Keep the original display text in `record` (or the
  snapshot) for results and highlights. Never display the token stream.
- Facet values are case-sensitive in the `raw` tokenizer. `venue:neurips` is case-insensitive in the
  language, so compile maps it to the stored spelling.
- Treat a tantivy-py upgrade as able to change scores or segment behaviour. Re-run determinism and
  differential suites, and bump `SCHEMA_VERSION` unless they prove the results identical.
