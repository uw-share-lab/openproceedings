# SQLite's INSERT OR REPLACE deletes a row without firing its DELETE trigger

**Key lesson:** An append-only SQLite table needs a `BEFORE INSERT … WHEN EXISTS (same key)` trigger as well as the `BEFORE UPDATE`/`BEFORE DELETE` ones, because `INSERT OR REPLACE` removes the old row without firing DELETE triggers unless the connection turned on `recursive_triggers`, which a plain `sqlite3` shell never does.

- **Date:** 2026-09-27 · **Task:** task-037 · **Area:** api
- **Artifacts:** `backend/src/openproceedings/records.py` (`_SCHEMA`, `RecordStore`), `backend/tests/unit/test_records.py`, `backend/tests/contract/test_records.py`

## What we set out to do
Search records (spec 04 §Search records): `POST /records`, the replay (`reproduced` / `drifted` /
`mismatch`), the diff, and an append-only `data/records/records.sqlite`.

## What we learned
- **REPLACE bypasses DELETE triggers.** With only `BEFORE UPDATE` and `BEFORE DELETE` triggers,
  `INSERT OR REPLACE INTO t VALUES('a','2')` over an existing `'a'` succeeds on a default connection and
  is refused only after `PRAGMA recursive_triggers = ON` (evidence: a two-connection check run while building
  task-037: `False replaced -> [('2',)]`, `True refused no`; SQLite's `lang_conflict.html` says the same).
  A `BEFORE INSERT` trigger fires before conflict resolution, so it refuses REPLACE, `INSERT OR IGNORE` and
  plain INSERT of a taken id from any client (`test_an_existing_id_is_never_replaced`, 8 cases).
- **The replay must re-run exactly what the save ran.** `records.identify` is `search.run(limit=0)` plus
  `match_ids`, used at save and at replay, so a record's `total` and `excluded` equal `/search`'s by
  construction (`test_post_freezes_every_field_of_spec_04s_table`).
- **The first 5 of the synthetic 5k corpus hold one default-passing record, and records 300–304 none**, so a
  "five removed, five added" drift fixture drifts to nothing under the defaults. The drift fixture uses 20
  and asserts `added and removed` are non-empty before checking exact counts.

## Dead ends — don't repeat these
- Relying on `recursive_triggers` set per connection: it protects only our own connections, not an
  operator's shell.
- Testing path traversal with `%2F` in a record id: Starlette decodes it before routing, so it never reaches
  the route (404 `API_NOT_FOUND`); malformed-id tests need characters that stay in one segment.

## Decisions (and what would change them)
- The record also stores `schema_version` and `ranking_params` (not in spec 04's table) → a drifted replay
  can name a method change after the pinned index is deleted → reverse only if the spec table grows them
  under another name.
- A pinned index this code can't open (another tokenizer or schema version) counts as unavailable, so its
  records replay as `drifted`, never `mismatch` → change if old engines are ever kept loadable.


## Follow-ups
- [ ] task-083 — `op record save/replay` (spec 08 CLI table) over `openproceedings.records`.
- [ ] task-084 — `semantic_version` set when the near-miss panel is open (deps task-060/062).
- [ ] task-085 — `op index retire` refuses while records pin a version (dep task-065).

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/skills/search-records/SKILL.md` §Store and §As built; spec 04
  §Search records "As built"; CLAUDE.md layout.
- Test or hook added? — `backend/tests/unit/test_records.py::test_an_existing_row_is_never_replaced`,
  `test_update_and_delete_are_refused_by_the_triggers`.

## Addendum — 2026-09-27 (task-037 review: REQUEST CHANGES)
- **"Couldn't compare" must not read as "everything changed".** A replay whose canonical no longer runs
  first reported every stored id as removed. Now `added`, `removed` and `membership_identical` are null
  when `refused` is set (`test_a_canonical_that_no_longer_runs_is_refused_with_null_counts`, both the
  drifted and mismatch paths).
- **An unauthenticated write endpoint needs a cost and a ceiling from day one.** Each save stored its whole
  id list, so repeated broad saves could fill the disk. Id lists are now content-addressed (`id_sets`;
  51 saves of one 20,000-id set grow the file by under 51 × 4 KiB, `test_identical_id_sets_are_stored_once`),
  the record routes cost the export weight, and a save into a store at its size cap or below the
  free-space floor is 503 `API_RECORDS_STORE_FULL`.
- **Read stored bodies with the types they were written with, not the live ones.** Validating a body
  against the live `DiagnosticCode` enum with `extra="forbid"` means retiring a code, or adding a field,
  makes every old record a 500. Bodies now carry `body_version` and are read with frozen, tolerant types;
  a committed v1 body with a retired code must stay readable (`test_a_committed_v1_body_stays_readable`).
- **WAL needs a writable directory, not a writable file.** SQLite writes `-wal` and `-shm` beside the
  database, so the store moved to its own `<data_dir>/records/` (0700), and spec 08's deploy note now names
  the directory.
- **Replay on the record's own index whenever it is here**, even when only the query version drifted, so
  `changed` isolates the one input that moved; and never trust a loader's engine without checking its
  `index_version` (`test_an_engine_of_another_version_is_never_used_as_the_pinned_one`).
- **A citation export hands over the stored set, not a re-run.** `/export?record_id=` streams the record's
  stored ids from its own index (409 if that index is gone), so a query-version change can never alter what
  screening receives (`test_a_record_exports_its_stored_ids_even_after_the_query_version_changed`, which
  fails on the earlier re-running route).
