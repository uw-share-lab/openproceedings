---
name: search-records
description: The search-record standard behind reproducibility (guarantee 4) and PRISMA reporting — which fields a record freezes, the exact ids_hash definition, the three replay statuses (reproduced / drifted / mismatch, all HTTP 200) and the diff endpoint, the append-only data/records.sqlite store, and what a methods section cites. Use when touching backend/src/openproceedings/api/records.py, POST/GET /records, the record page, or anything that changes what a stored record means.
---

# Search records (spec 04 §Search records)

A search record is the citable artifact of a review search: "we ran *this* canonical query against
*this* snapshot on *this* date and got *these* papers". It is written once and never edited.

## Fields (all required unless marked)
| Field | Source |
|---|---|
| `record_id` | a short, URL-safe, unguessable id (random, collision-checked on insert) |
| `input`, `mode`, `canonical`, `canonical_hash`, `identification_query` | 02's `ParseResult`. `identification_query` is the canonical string with the default conjuncts removed: the string that reproduces "identified" |
| `index_version`, `tokenizer_version`, `query_version`, `snapshot_hash`, `crawl_dates` (per source, from the manifest) | the database version and when its contents were collected |
| `searched_at` | UTC, ISO 8601 with `Z`. The search date, which is separate from the crawl date |
| `total`, `excluded` (with `unknown` itemised) | the counts cited in PRISMA; `excluded` is 03's per-filter breakdown, verbatim |
| `expansions`, `translations`, `warnings` | how the query was interpreted (PRISMA-S) |
| `ids` (sorted) and `ids_hash` | membership, for replay and for the diff; see below |
| `dedup` (`merged`, `ambiguous_not_merged` counts from the manifest) | the dedup process, for PRISMA-S |
| `semantic_version` | optional. Set only if the near-miss panel was open when the record was made (spec 06). **Never** an input to `ids_hash`. |

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
which `index_version` inputs changed. Replay re-parses `canonical`, not `input`, so compatibility
translations that changed later cannot alter the replay.

## Store: `data/records.sqlite`
- **Append-only.** The only statement allowed is `INSERT`. Add `BEFORE UPDATE` and `BEFORE DELETE`
  triggers that `RAISE(ABORT, …)`, and a test that tries both.
- A `schema_version` table. Migrations only add columns or tables and never rewrite rows.
- Open it with WAL mode. It is the one writable file on the otherwise read-only data volume (08 §Deploy).
- It is backed up with the snapshots and never committed (`data/` is gitignored).
- `POST /records` re-runs the query server-side to compute `total`, `excluded` and `ids_hash`. Never trust
  counts sent by the client.

## What a methods section cites
The record page (05) shows, and a methods section quotes: the `identification_query` and the default
clauses, the **full** `index_version` (never a prefix), the search date and the crawl date (separately),
`total`, the `excluded` breakdown with `unknown` on its own line (PRISMA "records removed before
screening", see `.claude/skills/prisma-reporting/SKILL.md`), the record URL, and the replay status on the
day it was checked. A `mismatch` record is not citable: the page shows "do not cite", with no methods text
and no export. RIS and BibTeX exports carry the same `index_version` and `canonical_hash` in `N1`/`note`, so a
Covidence library can be traced back to its record.

## Tests (spec 04 §Testing)
- Reproduced path: create a record on the fixture index, then replay it and get `reproduced`.
- Drifted path: build a second fixture index with records added and removed, then replay and check that
  the `added`/`removed` counts are exact.
- Mismatch path: corrupt a stored `ids_hash` (and, separately, a stored `excluded`) and expect HTTP 200
  with status `mismatch` and an ERROR log with code `API_REPLAY_MISMATCH`, never `drifted`.
- The append-only triggers fire. The `ids_hash` known-answer vectors hold.
