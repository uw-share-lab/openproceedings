---
name: index-versioning
description: How reproducibility is pinned (guarantee 4) — the index_version formula, the data/indexes/<index_version>/ layout and the `current` pointer, loading pinned older versions to replay search records, how it relates to canonical_hash, and exactly when TOKENIZER_VERSION or SCHEMA_VERSION must be bumped. Use when changing anything that could alter matches, scores or order, when building or promoting an index, or when a search record reports drifted.
---

# Index versioning (spec 03 §Versioning, spec 04 §Search records)

## The formula
```
index_version = sha256( snapshot_hash, TOKENIZER_VERSION, SCHEMA_VERSION, ranking_params )[:12]
```
- Hash a **canonical serialization** of the four inputs (for example, JSON with sorted keys and no
  whitespace, and ranking floats written the same way every time). Pin the serialization with a unit test
  on known inputs. If it changes, every version id changes.
- `canonical_hash = sha256(canonical + TOKENIZER_VERSION)` identifies the *query*. `index_version`
  identifies the *index*. A search record stores both, plus `ids_hash = sha256(sorted matched ids)`.

## Layout and lifecycle
```
data/indexes/<index_version>/   immutable Tantivy dir + manifest
data/indexes/current            symlink → the served version
```
- Built only by `op index build` (`.claude/skills/tantivy-indexing/SKILL.md`). Never edited, rebuilt in
  place, or committed. `protect-data-dir.sh` blocks writes, and `data/` is gitignored.
- Promotion: build offline → run the differential, parity and determinism suites → switch `current`
  atomically → SIGHUP the API. The API swaps its pointer atomically, and in-flight requests finish on the
  old version.
- Keep every version referenced by a search record in `data/records.sqlite`. Check before deleting any.
- The API loads a **pinned** older version to replay a record (`.claude/skills/search-records/SKILL.md`).
  Same version available and `ids_hash` equal → `reproduced`. Otherwise → `drifted`, with a diff.

## Bump rules
| Change | Bump |
|---|---|
| Any input could tokenize differently (`normalize.py`, LaTeX rules, the analyzer) | `TOKENIZER_VERSION` (rule in `.claude/skills/token-contract/SKILL.md`) |
| Index field set, field type, index options (positions, freqs), stored layout, analyzer registration, how a field is populated (e.g. missing abstract → `""`) | `SCHEMA_VERSION` |
| Weights, k1, b, sort definitions | nothing to bump. They are in `ranking_params` already, so `index_version` changes |
| A tantivy-py upgrade | `SCHEMA_VERSION`, unless the determinism and differential suites prove identical IDs, order and scores |
| New snapshot | nothing to bump; `snapshot_hash` changes |
| Pure refactor proven identical by parity + determinism | none |

When in doubt, bump. A needless bump makes an old record report `drifted` when it didn't have to. A missed
bump makes a record claim `reproduced` when its results changed, which is the one failure that invalidates
a systematic review.

## Checklist
- [ ] the serialization test still passes, or the change is intentional and noted in a decision record
- [ ] the manifest records all four inputs and the tantivy-py version
- [ ] responses carry `index_version` and `tokenizer_version` (spec 04)
- [ ] a record replay test covers the path the change touched
