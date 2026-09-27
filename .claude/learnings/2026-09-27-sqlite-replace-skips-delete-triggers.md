# SQLite's INSERT OR REPLACE deletes a row without firing its DELETE trigger

**Key lesson:** An append-only SQLite table needs a `BEFORE INSERT … WHEN EXISTS (same key)` trigger as well as the `BEFORE UPDATE`/`BEFORE DELETE` ones, because `INSERT OR REPLACE` removes the old row without firing DELETE triggers unless the connection turned on `recursive_triggers`, which a plain `sqlite3` shell never does.

- **Date:** 2026-09-27 · **Task:** task-037 · **Area:** api
- **Artifacts:** `backend/src/openproceedings/records.py` (`_SCHEMA`, `RecordStore`), `backend/tests/unit/test_records.py`, `backend/tests/contract/test_records.py`

## What we set out to do
Search records (spec 04 §Search records): `POST /records`, the replay (`reproduced` / `drifted` /
`mismatch`), the diff, and an append-only `data/records.sqlite`.

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
- [ ] `op record save/replay` (spec 08 CLI table) over `openproceedings.records` — to be filed after the M3a
  merge (listed in task-037's notes; not created on this branch to avoid colliding task ids with the
  concurrent task-036/038 branches).
- [ ] `semantic_version` set when the near-miss panel is open (M5, with task-060/062) — same.

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/skills/search-records/SKILL.md` §As built; spec 04 §Search
  records "As built"; CLAUDE.md layout.
- Test or hook added? — `backend/tests/unit/test_records.py::test_an_existing_id_is_never_replaced`,
  `test_update_and_delete_are_refused_by_the_triggers`.
