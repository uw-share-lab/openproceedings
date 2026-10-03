---
id: decision-030
title: >-
  Index ord at SCHEMA_VERSION 3 and keep serving schema 2 until no record pins a
  schema-2 index (TASK-167)
date: '2026-10-03 01:25'
status: accepted
---
## Context

A position-verified clause compiles to its candidate query narrowed by the ids that held the check (or less the
candidates that failed, when they are fewer: TASK-076). Up to schema 2 those ids are a term set on the text `id`,
which Tantivy resolves again on every search. TASK-076 measured the synthetic `"AI agent$"` clause's set
(20,752 ids) at about 10 ms. Removing that cost needs either a reusable id set, which tantivy-py 0.26 doesn't
expose, or an indexed per-document number to name the documents by. `ord` is already a fast column, and
indexing it changes the schema.

A plain `SCHEMA_VERSION` bump would make `unservable` refuse every existing index. A search record pinned to one
could then never replay `reproduced` again (guarantee 4).

Measured (`docs/results/2026-10-02-exclusions-and-verified-forms.md`, old and new alternated, load 30–155):
- The `"AI agent$"` id set alone: 11.3 ms CPU on the text `id`, 6.2 ms on the indexed `ord`.
- `main-2-pop`'s warm search, CPU p50: 29.4 vs 29.7 ms on the synthetic 80k, and 26.4 vs 25.6 ms (about 3%)
  on the real M4 corpus. Every other Trust-Evals string is unchanged. Inside a search the id set is one MUST
  clause of an intersection the rarer clauses drive, so most of its isolated cost never reaches a search.
- The one form with no id list that tantivy-py offers, a constant-0 `regex_phrase_query`, matched the same ids
  but cost 2–4x the id set.

## Decision

- `SCHEMA_VERSION` 3 indexes `ord`. In a schema-3 index, a verified clause names its ids as a u64 term set on
  `ord` (`TantivyEngine.id_set`).
- The code serves two schemas. `engine/index.py`'s `SERVED_SCHEMAS` maps the current schema and the previous
  one to a `SchemaForm`, which records what differs between them (`ord_indexed`). `unservable` accepts both. The
  engine reads its index's form from the manifest and branches on that, never on a version string. A schema-2
  index keeps the text-`id` term set.
- Kept by owner decision (2026-10-02), after the end-to-end numbers above: the change is exact and replay-safe,
  and its gain is small.

## Consequences

- Guarantee 4 holds across the bump. Records saved by the pre-change code on the real `05a0541717f6` index
  (all 10 Trust-Evals strings) replayed `reproduced` with a schema-3 build served and `05a0541717f6` pinned.
  `tests/contract/test_records.py` checks the same through the API on the 5k corpus.
- Both schemas give the same ids and the same float scores for every query: `test_served_schemas.py`, and
  `test_verified_exclusion.py` on both schemas.
- Every rebuild gets a new `index_version`, and a record saved on a schema-3 index names schema 3 among its
  inputs.
- **Retiring schema 2:** rebuild every served index at schema 3, repoint `current`, then `op index retire` each
  schema-2 version, which `op index retire` refuses while any record pins it. Once no schema-2 index is pinned,
  drop "2" from `SERVED_SCHEMAS` together with its path and its tests. A third schema retires the oldest first,
  so at most two are ever served.
- A tantivy-py upgrade still strands old indexes (the engine refuses another Tantivy's index), whatever
  `SERVED_SCHEMAS` holds (index-versioning skill).
- The same pattern serves two `TOKENIZER_VERSION`s if a tokenizer change must keep old indexes replayable: a
  per-index form, read from the manifest, that the engine branches on.
