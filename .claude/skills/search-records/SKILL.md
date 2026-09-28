---
name: search-records
description: The search-record standard behind reproducibility (guarantee 4) and PRISMA reporting — which fields a record freezes, the exact ids_hash definition, the three replay statuses (reproduced / drifted / mismatch, all HTTP 200) and the diff endpoint, the append-only data/records/records.sqlite store, and what a methods section cites. Use when touching backend/src/openproceedings/api/records.py, POST/GET /records, the record page, or anything that changes what a stored record means.
---

# Search records (spec 04 §Search records)

A search record is the citable artifact of a review search: "we ran *this* canonical query against
*this* snapshot on *this* date and got *these* papers". It is written once and never edited.

## Fields (all required unless marked)
| Field | Source |
|---|---|
| `record_id` | a short, URL-safe, unguessable id (random, collision-checked on insert) |
| `input`, `mode`, `canonical`, `canonical_hash`, `identification_query` | 02's `ParseResult`. `identification_query` is the canonical string with the default conjuncts removed: the string that reproduces "identified" |
| `index_version`, `tokenizer_version`, `query_version`, `snapshot_hash`, `crawl_dates` (the corpus-wide `*` from–to summary plus each claim source's own manifest window when available) | the database version and when its contents were collected |
| `crawl_dates_kind` (body v2; per `crawl_dates` key) | what those dates are: `crawl` (fetch times, UTC), `scholar_query_dates` (a bootstrap source's Publish or Perish query dates: local time labelled UTC, so an end can be a day off; say "Scholar searches run …", never "a crawl"), or `mixed` (`*` over both kinds) |
| `sources` (body v2) | the snapshot manifest's source names, sorted |
| `identification_citable` (body v2) | `false` when every source is a bootstrap one (`vocab.bootstrap_only`, the same test as `op search`'s "note: bootstrap corpus"): the counts describe an earlier search's output, not a database, so they are not PRISMA identification numbers. The record page then shows that caution and no methods text |
| `searched_at` | UTC, ISO 8601 with `Z`. The search date, which is separate from the crawl date |
| `total`, `excluded` (with `unknown` itemised) | the counts cited in PRISMA; `excluded` is 03's per-filter breakdown, verbatim |
| `expansions`, `translations`, `warnings` | how the query was interpreted (PRISMA-S) |
| `ids` (sorted) and `ids_hash` | membership, for replay and for the diff; see below |
| `dedup` (`merged` and the manifest's not-merged conflicts by resolution: `ambiguous_not_merged`, and from body v2 `track_not_merged`, `venue_year_not_merged`) | the PRISMA-S item 16 deduplication-process statement (corpus-wide ingest merges, never a per-search removal count; `prisma-reporting`) |
| `semantic_version` | optional. Set only if the near-miss panel was open when the record was made (spec 06). **Never** an input to `ids_hash`. |
| `schema_version`, `ranking_params` | as built (task-037): the index's other two `index_version` inputs, so a drifted replay names a method change even after the pinned index is deleted |

Store the full sorted id list as well as the hash, compressed if needed. The diff cannot say *which*
papers were added or removed without it.

## `ids_hash`
`sha256("\n".join(sorted(ids)).encode("utf-8")).hexdigest()`. Ids are sorted as Python `str` (code
point order), with no trailing newline. Pin this in exactly one function, with a known-answer test (the
empty set, one id, three ids). Changing the serialisation silently turns every old record into
`drifted`. The hash covers **membership only**: sort, ranking params and the semantic layer never
enter it (guarantee 5).

## Replay (`GET /records/{id}`)
Every replay returns **HTTP 200** with a `status`:

| Situation | Status | Response adds |
|---|---|---|
| The same `index_version` **and** `query_version` are available, and both `ids_hash` **and** `excluded` match | `reproduced` | — |
| Only a different index or query version is available | `drifted` | *which* inputs changed (`snapshot_hash` = corpus drift; tokenizer, schema, ranking or query version = method drift), `+added / −removed`, the version it ran on. `+0 / −0` is reported as "membership-identical", not hidden |
| Same `index_version` and `query_version`, but `ids_hash` or `excluded` differ | `mismatch` | This breaks guarantee 4: log at ERROR with code `API_REPLAY_MISMATCH` and treat it as a Must bug. Never report it as `drifted`. The record page shows "do not cite" (05) |

The diff behind `drifted` is `GET /api/v1/records/{id}/diff`: added and removed ids (with titles), and
which `index_version` inputs changed. An export pinned to a `mismatch` record (`/export?record_id=`) is
refused with 409 `API_RECORD_MISMATCH` (spec 04 §Error handling).

**A withheld replay** (decision-010, round 3): a canonical with more position-verified clauses than
`max_verified_clauses`, or whose checks would read more than `max_verification_candidates` documents, is
not run on this instance (`replay(admit=…)`, the API's `deps.admit_replay`, called with the engine the
replay runs on). It is 200, never a 422: `refused` is `API_TOO_MANY_VERIFIED_CLAUSES` or
`API_QUERY_TOO_COSTLY`, counts null, `verified_clauses` set, nothing compiled or charged for its clauses.
On its own index under its own query version it is `drifted` with `changed: []` (the status enum is
closed; a `withheld` status was rejected), never `reproduced` and never a `mismatch` for the withholding;
the run-free checks (canonical re-parse, index inputs, stored list hash and total) still make it a
`mismatch` if they fail. `/export?record_id=` still streams the stored ids. The record page says
"could not be re-run: <code> — this instance's limit is below the record's N position-verified clauses".

Replay re-parses `canonical` (once per request: the API passes the parse it counted to `replay`), not `input`, so compatibility
translations that changed later cannot alter the replay.

## Store: `data/records/records.sqlite`
- **Its own directory** (`<data_dir>/records/`, mode 0700; the file 0600): WAL mode writes `-wal` and `-shm`
  beside the database, so the directory must be writable. It is the one writable place on the otherwise
  read-only data volume (08 §Deploy). Backed up with the snapshots, never committed (`data/` is gitignored).
- **Append-only.** The only statement the code issues is `INSERT` (plus `CREATE … IF NOT EXISTS`). Every
  table has `BEFORE UPDATE` and `BEFORE DELETE` triggers that `RAISE(ABORT, …)`, and `records` and
  `id_sets` a `BEFORE INSERT … WHEN EXISTS (same key)` trigger: SQLite's REPLACE deletes the old row
  *without* firing DELETE triggers unless `recursive_triggers` is on, so update/delete triggers alone don't
  stop `INSERT OR REPLACE` from a plain `sqlite3` shell. Tests try each.
- **The triggers are not a security boundary.** They stop mistakes (a stray `UPDATE`, a REPLACE); anyone
  with write access to the file can drop them. Protect the file with the volume's permissions.
- A `schema_version` table (currently 1). Migrations only add columns or tables and never rewrite rows; a
  store with a newer version is refused.
- **The first migration needs an explicit step.** `schema_version` is checked only when the store is opened
  for a write (`_ensure`, on the first insert), never on a read, and every schema statement is
  `CREATE … IF NOT EXISTS`, which never replaces an existing table or a *changed* trigger. So the first
  migration must (1) insert the new version row, (2) `DROP TRIGGER` and re-create any trigger whose text
  changed, and (3) be checked on read paths too, or an old instance would read a new store unchecked.
- **`RecordStore.insert` refuses** fields whose `ids_hash` isn't the hash of the ids passed (500), so a
  row that could only ever replay as a mismatch is never written. Tests that need such a row (replay and
  export of a broken record) write it straight into the file, as `tampered()` in
  `backend/tests/contract/test_records.py` does.
- **`excluded` is compared whole** on replay (`Excluded.to_json()` against the stored `Excluded`, the one schema of the exclusion accounting), so
  its shape is covered by `query_version`: adding a key to the live shape without a `query_version` bump
  would turn every stored record into a `mismatch`. `test_the_stored_excluded_shape_is_the_live_one` fails
  first.
- **Content-addressed id sets:** `id_sets (ids_hash, ids)` holds each distinct id list once (zlib of the
  `\n`-joined sorted list, re-hashed against its key on every read); `records (record_id, index_version,
  searched_at, id_set, body)` points at it. Saving the same set again costs one body (~1 KB).
- **Bodies are versioned** (`body_version`, now 2) and read with frozen, tolerant types (a diagnostic's
  `code` is a string, unknown keys ignored), so changing a live enum never makes an old record unreadable.
  `backend/tests/fixtures/records/record-v1.json` must stay readable; a newer `body_version` is a 500.
  v2 added `sources`, `identification_citable`, `crawl_dates_kind` and two `dedup` counts: a v1 body reads
  them as null ("not recorded", never guessed), and a v2 body without them, or whose
  `identification_citable` contradicts its `sources`, is refused as unreadable.
- **Capacity:** a save is refused (503 `API_RECORDS_STORE_FULL`) when the store is at
  `ApiConfig.records_max_bytes` or its disk below `records_min_free_bytes`. All three record routes cost the
  rate limit's `export_weight` (but `GET /records/{id}?replay=false`, which runs nothing: one token).
- `POST /records` re-runs the query server-side to compute `total`, `excluded` and `ids_hash`. Never trust
  counts sent by the client.

### Takedown runbook (the one sanctioned deletion)
A record must go (a legal request, personal data in `input`). With the API stopped:
1. Back up `records/` (all three files).
2. `sqlite3 data/records/records.sqlite`: `DROP TRIGGER records_no_delete;`, then
   `DELETE FROM records WHERE record_id = '<id>';`. Leave `id_sets` alone (other records may share the set).
3. Re-create the trigger exactly as `records.py`'s `_SCHEMA` declares it (starting the API also re-creates any
   missing trigger: every statement is `CREATE … IF NOT EXISTS`), and check `.schema records` shows all
   three triggers.
4. Record the takedown (date, id, reason, who) in the operator log; the record page then 404s.

## As built (task-037 and its review fixes)
- Code: `backend/src/openproceedings/records.py` (`ids_hash`, `SearchRecord`, `identify`, `freeze`,
  `RecordStore`, `replay`), `api/records.py` (routes and the `/export` hook), `IndexState.pinned` in
  `api/state.py` (older indexes, loaded on demand read-only; the one loader, shared with `/export`). Tests: `backend/tests/unit/test_records.py` (known answers, triggers, id sets,
  capacity, tolerant bodies, manifest checks, concurrency) and `backend/tests/contract/test_records.py` (the
  replay matrix, refused replays, diff pages, ids on request, cost, errors, logs).
- `identify` is the one membership computation, at save and at replay: `search.run` (so `total`/`excluded`
  equal `/search`'s) plus `match_ids`.
- Replay runs on the record's own index whenever it is here (even when only the query version drifted, so
  `changed` isolates that), and an engine handed back for another version counts as unavailable. A refused
  replay (the canonical no longer runs, or is withheld) reports `added`/`removed`/`membership_identical` as
  null, never "everything removed".
- `RecordStore.insert` refuses fields whose `ids_hash` isn't its ids' hash or whose `total` isn't their
  number (either could only replay as a mismatch); tests that need such a row write it with raw SQL.
- `API_REPLAY_MISMATCH` is ERROR once per record per process, DEBUG after that.
- `GET /records/{id}` leaves `ids` out unless `?include=ids`; `/diff` pages each list (`offset`, `limit` ≤
  200) and keeps `added_total`/`removed_total` in full.
- A mismatch test adds a *new* row, never an edit: a copy with a wrong `ids_hash`, `excluded`, one bucket,
  `canonical_hash`, a non-canonical `canonical`, or a stored list `ids_hash` doesn't name. It is written
  straight into `records.sqlite` with plain `INSERT`s (`tampered` in `backend/tests/contract/test_records.py`),
  as a broken writer would, because `RecordStore.insert` refuses a row whose `ids_hash` isn't its list's.
  The triggers allow a new row, so the store stays append-only in tests too.
- `/export?record_id=` hands over exactly the cited set: the record's **stored** ids, from the index it
  names, never a re-run of the query (so a later query version changes nothing). 409
  `API_INDEX_VERSION_UNAVAILABLE` when that index is gone; 409 `API_RECORD_MISMATCH` when the replay is a
  `mismatch` (`api.records.stored_record`, then `refuse_mismatch` on the pinned index). A `reproduced`
  replay also requires the stored list to hash to `ids_hash`. Spec 04 §Search records "As built" has the
  full response shapes.
- UI additions (TASK-090/091, additive): `record.identified_total` / `unclassified_total` are computed
  fields (`total + excluded.total`; the two `unknown` buckets), derived on read and **never stored**
  (`records.DERIVED` is excluded from the body), so old bodies have them and none can disagree with its own
  counts; `replay.*` carries the replay's (null when refused). `POST /records {…, index_version}` refuses a
  save on any index but that one (409 `API_INDEX_VERSION_UNAVAILABLE`, checked before the parse and the save
  ceilings). `GET /records/{id}?replay=false` is the stored record with `replay: null`, no run, one token,
  answered during `API_BUSY` (decision-014: the only v1 field allowed to become nullable).

## The record page and the methods text (TASK-044; spec 05 §Components 8 *As built*)
`frontend/src/components/record/record-view.tsx` reads `?replay=false` first and the replay second; the
methods text (`frontend/src/lib/methods-text.ts`) and the record's exports (`/export?record_id=` only) wait for
the replay, so a `mismatch` renders neither. Every number the page and the methods text show is a record field;
`record-fixture.json` (real API answers, `backend/tests/contract/record_fixture.py`) pins them in the tests.

## The CLI: `op record save` / `op record replay` (task-083; spec 08 §CLI)
- The same functions: `save` is `records.freeze` + `RecordStore.insert` (the record equals `POST /records`'s
  for the same query and index in every field but `record_id` and `searched_at`; tested), `replay` is
  `records.replay` with its `--json` block built by `api.records.replay_info`, the function behind
  `GET /records/{id}`'s `replay`.
- Index selection is the API's (`api.state.index_path`): `--index current|<index_version>` under
  `<data-dir>/indexes`, never a directory path and never `resolve_snapshot`. A replay opens the record's own
  version first (`api.state.open_pinned`, the one function behind `IndexState.pinned`, used without the
  server's cache, open slot and verification gate, so its refusals are the same lines at the same levels) and
  only falls back to `--index`/`current` when it is gone.
- Serving policy is left out: no rate limit or save ceilings, and no `admit`, so a CLI replay is never
  withheld (the API may report `refused: API_TOO_MANY_VERIFIED_CLAUSES` for a record the CLI reproduces). So
  `save` counts the query's verified clauses and candidates against `ApiConfig`'s defaults (16, 300,000) and,
  over either, prints a note to stderr (user output, not a log line) naming the code a default-configured
  instance would refuse it and withhold its replay with. The store's size cap and free-space floor apply,
  with `ApiConfig`'s defaults.
- Exit status: 0 `reproduced` or `drifted`, 3 `mismatch` (`cli.EXIT_MISMATCH`; ERROR `API_REPLAY_MISMATCH`),
  1 for an unknown or malformed id or no index to replay on. Log lines `record_saved` / `record_replayed`
  carry the id, versions, `canonical_hash` and counts (`record_replayed`: `status`, both index versions,
  `query_version`, `total`, `added_total`, `removed_total`, `refused`), never the query; `record_saved` is
  logged before the output is printed.
- Tests: `backend/tests/contract/test_record_cli.py` (the API-equality check, the replay matrix through the
  CLI, the exit codes across a real process, the store floor, no query text in logs).

## What a methods section cites
The record page (05) shows, and a methods section quotes: the `identification_query` and the default
clauses, the **full** `index_version` (never a prefix), the search date and the crawl window
(`crawl_dates["*"]` from–to; separately), `total`, the `excluded` breakdown with `unknown` on its own line
(PRISMA "records removed before screening", see `.claude/skills/prisma-reporting/SKILL.md`), the record
URL, and the replay status on the day it was checked. A `mismatch` record is not citable: the page shows
"do not cite", with no methods text and no export. A record whose `identification_citable` is not `true`
(a bootstrap corpus, or a v1 record that didn't record it) gets the CLI's caution and no methods text; its
exports still work. RIS and BibTeX exports carry the same `index_version` and `canonical_hash` in
`N1`/`note`, and an export from the record page (`/export?record_id=`) adds `record <record_id> · searched
<date>`, so a Covidence library can be traced back to its record.

## Tests (spec 04 §Testing)
- Reproduced path: create a record on the fixture index, then replay it and get `reproduced`.
- Drifted path: build a second fixture index with records added and removed, then replay and check that
  the `added`/`removed` counts are exact.
- Mismatch path: corrupt a stored `ids_hash` (and, separately, a stored `excluded`) and expect HTTP 200
  with status `mismatch` and an ERROR log with code `API_REPLAY_MISMATCH`, never `drifted`.
- The append-only triggers fire. The `ids_hash` known-answer vectors hold.
