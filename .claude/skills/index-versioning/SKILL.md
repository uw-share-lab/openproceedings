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
- `canonical_hash = sha256(canonical + "\0" + TOKENIZER_VERSION + "\0" + QUERY_VERSION)` (decision-003)
  identifies the *query*. `index_version`
  identifies the *index*. A search record stores both, plus `ids_hash = sha256(sorted matched ids)`.

## `query_version` (spec 04 §Conventions)
`query_version` versions the query *semantics* that live **outside** the index: the parser, the compiler
(NEAR/slop, wildcard rules), the default-filter set and the `source:` alias table. It is not an input to
`index_version`, so a parser or compiler change never changes the index id; it changes `query_version`
instead. It is bumped by the same rule as `TOKENIZER_VERSION`: whenever some query could mean something
different. `TOKENIZER_VERSION` covers normalization (shared by both sides, and inside `index_version`);
`query_version` covers everything the query side adds on top. Every response carries all three:
`index_version`, `tokenizer_version`, `query_version`, and a search record stores all three.

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
- Keep every version referenced by a search record in `data/records/records.sqlite`. Delete an old version
  only with `op index retire <index_version>` (TASK-085; spec 08 §CLI), never by hand. It refuses (exit 1,
  nothing touched) while `RecordStore.pinned(version) > 0` (it reports the count: a deleted pinned index
  would leave those records' replays permanently `drifted`), while `current` or another symlink in
  `indexes/` points at the version, when the record store can't be read, and when the name isn't an
  index_version directory directly under `indexes/` (the format is checked before any path is built).
  `--dry-run` runs the same checks and deletes nothing. Order: repoint `current` to the new version, SIGHUP the API, confirm `/api/v1/meta` reports the new version, then retire the old one (the API keeps serving the old version until its reload). It can't see an
  `op serve --index <version>` that serves the version by name, so check each running instance first. A save
  or a promotion takes no indexes lock, so retire checks the pins and the symlinks once more after renaming
  the directory aside (`.retiring-<version>`, never swept), and renames it back on a hit or on anything raised,
  Ctrl-C included; only the few syscalls before the removal remain open. A failed rename-back logs ERROR
  `index_retire_restore_failed`: `mv indexes/.retiring-<version> indexes/<version>` by hand before anything else;
  until then every retire of that version is refused as `retire_cut_short`.
- The API loads a **pinned** older version to replay a record (`.claude/skills/search-records/SKILL.md`).
  Replay returns HTTP 200 with one of three statuses (spec 04 §Search records):
  - **`reproduced`**: the same `index_version` **and** `query_version` are available, and both `ids_hash`
    **and** `excluded` match.
  - **`drifted`**: only a different index or query version is available. Name *which* inputs changed
    (`snapshot_hash` = corpus drift; tokenizer, schema, ranking or query version = method drift) and give
    `+added / −removed`. `+0 / −0` is reported as "membership-identical", not hidden.
  - **`mismatch`**: same `index_version` and `query_version`, but `ids_hash` or `excluded` differ. This
    breaks guarantee 4: log at ERROR with code `API_REPLAY_MISMATCH` and treat it as a bug.

## Bump rules
| Change | Bump |
|---|---|
| Any input could tokenize differently (`normalize.py`, LaTeX rules, the analyzer) | `TOKENIZER_VERSION` (rule in `.claude/skills/token-contract/SKILL.md`) |
| Index field set, field type, index options (positions, freqs), stored layout, analyzer registration, how a field is populated (e.g. missing abstract → `""`) | `SCHEMA_VERSION`, and keep serving the previous one (§Two served schemas) |
| Weights, k1, b, sort definitions | nothing to bump. They are in `ranking_params` already, so `index_version` changes |
| A tantivy-py upgrade | `SCHEMA_VERSION`, always: Tantivy is not an `index_version` input, and the engine refuses an index built with another Tantivy (`unservable`), so without the bump the new code could neither serve the old index nor build a new id (`op index build` finds the id and keeps the old directory). `changelog.py --release` refuses a release that changes Tantivy alone (spec 08 §Release). Upgraded by hand only: Dependabot's `uv` entry ignores `tantivy` (TASK-150), because a bump merged alone would leave `dev` unable to serve or build an index; an `ignore` was chosen over a CI check as the simpler gate for a rare, hand-verified upgrade. The path: bump the `tantivy==` pin in `backend/pyproject.toml`, `uv lock`, bump `SCHEMA_VERSION` in `engine/index.py`, rebuild and verify an index (spec 08 §Deploy runbook) |
| Parser, compiler (NEAR/slop, wildcard rules), default-filter set, `source:` alias table: any change that could make some query mean something different | `query_version` (not part of `index_version`) |
| New snapshot | nothing to bump; `snapshot_hash` changes |
| Pure refactor proven identical by parity + determinism | none |

## Two served schemas (TASK-167)
A `SCHEMA_VERSION` bump changes every new `index_version`, but it must not strand the indexes that search records
pin. So `engine/index.py` lists `SERVED_SCHEMAS`, the current schema and the one before it, and `unservable`
accepts both. New builds use the current schema. An index of the previous schema is opened as it was built, and
the engine takes that schema's path for it (schema 2: a verified clause's ids as a term set on the text `id`;
schema 3: on the indexed `ord`; `TantivyEngine.ord_indexed`). The two paths must give the same ids and the same
float scores for every query (`test_served_schemas.py`). A record saved on the old schema must replay
`reproduced` on its own index after the bump (`test_records.py::…schema_2…`), and the same holds against a
real index, checked locally. Retiring the old schema: rebuild every served index at the new schema, repoint
`current`, and `op index retire` each old version once no record pins it. Only then drop the schema from
`SERVED_SCHEMAS`, with its path and its tests. A third schema while two are served first retires the oldest.
A tantivy-py upgrade is different: the engine refuses an index built by another Tantivy, so it strands old
indexes whatever `SERVED_SCHEMAS` holds.

When in doubt, bump. A needless bump makes an old record report `drifted` when it didn't have to. A missed
bump makes a record claim `reproduced` when its results changed, which is the one failure that invalidates
a systematic review.

## Checklist
- [ ] the serialization test still passes, or the change is intentional and noted in a decision record
- [ ] the manifest records all four inputs and the tantivy-py version
- [ ] responses carry `index_version`, `tokenizer_version` and `query_version` (spec 04)
- [ ] a record replay test covers the path the change touched
