---
name: search-records
description: The search-record standard behind reproducibility (guarantee 4) and PRISMA reporting — which fields a record freezes, the exact ids_hash definition, reproduced vs drifted replay (and what a same-version mismatch means), the append-only data/records.sqlite store, and what a methods section cites. Use when touching backend/src/openproceedings/api/records.py, POST/GET /records, the record page, or anything that changes what a stored record means.
---

# Search records (spec 04 §Search records)

A search record is the citable artifact of a review search: "we ran *this* canonical query against
*this* snapshot on *this* date and got *these* papers". It is written once and never edited.

## Fields (all required unless marked)
| Field | Source |
|---|---|
| `record_id` | a short, URL-safe, unguessable id (random, collision-checked on insert) |
| `input`, `canonical`, `canonical_hash`, `mode` | 02's `ParseResult` |
| `index_version`, `tokenizer_version` | the engine that served the search |
| `created_at` | UTC, ISO 8601 with `Z` |
| `total` | the lexical matched-set size |
| `excluded` | 03's per-filter exclusion counts, verbatim |
| `ids_hash` | see below |
| `semantic_version` | optional. Set only if the near-miss panel was visible when the record was made (spec 06). **Never** an input to `ids_hash`. |

Store the full sorted id list as well as the hash, compressed if needed. The drift report cannot say
*which* papers were added or removed without it.

## `ids_hash`
`sha256("\n".join(sorted(ids)).encode("utf-8")).hexdigest()`. Ids are sorted as Python `str` (code
point order), with no trailing newline. Pin this in exactly one function, with a known-answer test (the
empty set, one id, three ids). Changing the serialisation silently turns every old record into
`drifted`. The hash covers **membership only**: sort, ranking params and the semantic layer never
enter it (guarantee 5).

## Replay (`GET /records/{id}`)
| Situation | Status | Response adds |
|---|---|---|
| The record's `index_version` can be loaded and the re-run hash equals `ids_hash` | `reproduced` | — |
| Only newer versions available; re-run on current | `drifted` | `added`, `removed` counts, the current `index_version`, a link to the id diff |
| Same `index_version` loaded, but the hash **differs** | not a valid replay status | This violates guarantee 4. Return a server error with code `replay_mismatch`, log it at error level, and treat it as a Must bug. Never report it as `drifted`. |

Spec 04 §Search records now defines all three statuses. In a mismatch, the record's status is `mismatch`,
logged at error level with code `replay_mismatch`. The diff behind `drifted` is
`GET /api/v1/records/{id}/diff` (added and removed ids with titles). Replay re-parses `canonical`, not `input`, so compatibility translations that changed later
cannot alter the replay.

## Store: `data/records.sqlite`
- **Append-only.** The only statement allowed is `INSERT`. Add `BEFORE UPDATE` and `BEFORE DELETE`
  triggers that `RAISE(ABORT, …)`, and a test that tries both.
- A `schema_version` table. Migrations only add columns or tables and never rewrite rows.
- Open it with WAL mode. It is the one writable file on the otherwise read-only data volume (08 §Deploy).
- It is backed up with the snapshots and never committed (`data/` is gitignored).
- `POST /records` re-runs the query server-side to compute `total`, `excluded` and `ids_hash`. Never trust
  counts sent by the client.

## What a methods section cites
The record page (05) shows, and a methods section quotes: the canonical query string, the database
("openproceedings, index `<index_version>`, snapshot of `<date>`"), the search date, `total`, the
`excluded` breakdown (PRISMA "records removed before screening", see
`.claude/skills/prisma-reporting/SKILL.md`), the record URL, and the replay status on the day it was
checked. RIS and BibTeX exports carry the same `index_version` and `canonical_hash` in `N1`/`note`, so a
Covidence library can be traced back to its record.

## Tests (spec 04 §Testing)
- Reproduced path: create a record on the fixture index, then replay it and get `reproduced`.
- Drifted path: build a second fixture index with records added and removed, then replay and check that
  the `added`/`removed` counts are exact.
- Tamper test: corrupt a stored hash and expect `replay_mismatch`, never `drifted`.
- The append-only triggers fire. The `ids_hash` known-answer vectors hold.
