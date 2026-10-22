# Stored string lengths, and what decision-053's caps change (TASK-279)

2026-10-22 · TASK-279 · decision-053 · read-only over the maintainer's snapshot; no snapshot or index was built,
moved or deleted.

decision-053 caps every stored string field that decision-026 left uncapped. Each cap was set from these
measurements, with at least 2.7 times the longest value held, so that the caps trim no record of the current corpus.

| | |
|---|---|
| Snapshot | `2026-10-16-03eab0ef56c4` (`snapshot_hash` `03eab0ef56c4d768ca25c1942207d1c9eaf14a1d852bd276a05e013ae17210c7`), 173,518 records, record schema 9, tokenizer 3 |
| Script | [`2026-10-22-stored-string-lengths-check.py`](2026-10-22-stored-string-lengths-check.py): `uv run python docs/results/2026-10-22-stored-string-lengths-check.py <snapshot>`, from the main checkout (where `data/` lives) or with the snapshot's absolute path (about 110 s) |
| Code | the TASK-279 branch at `9e0af863` (decision-053's caps as the branch ships them); an earlier run at the round-1 code gave the same result |
| Counted | in NFKD, as `ingest/caps.py` counts; every claim, losing claims included |

## The longest value of each field

| Field | Longest | Cap | Ratio |
|---|---|---|---|
| DOI (`urls.doi`, record and claim) | 34 | 1,000 | 29× |
| URL (`urls.pdf`, record and claim; the longest of the three URL slots) | 154 | 2,048 | 13× |
| `urls.proceedings` | 135 | 2,048 | 15× |
| `urls.forum` | 52 | 2,048 | 39× |
| a claim's `url` | 154 | 2,048 | 13× |
| author name (record and claim) | 81 | 1,000 | 12× |
| keyword (record and claim) | 733 | 2,000 | 2.7× |
| `venue_id_raw` (record and claim) | 65 | 500 | 7.7× |
| an `invitation` claim's value | none held | 500 | |
| a claim's `evidence` | 469 | 4,000 | 8.5× |
| `id` (not capped; TASK-281) | 53 | | |

At most 95 authors and 54 keywords on one record (not capped; TASK-280).

- **The 733-character keyword** is ICLR 2025 `d8hURACo0P`: its authors put abstract sentences in OpenReview's keywords
  field, which the source splits at commas. A real keyword is far shorter, which is why the keyword cap has the least
  headroom.
- **The 469-character evidence** is an AAAI 2005 dblp record's track claim, which quotes its official-contents section
  and two Internet Archive URLs.

## What the caps change

`cap_record`, with decision-053's caps, over every record: `records=173518 changed=0 flagged=26`. No record changes,
and the 26 flagged are the records decision-026 already trimmed (the manifest's `trimmed` lists the same 26). So
`records.jsonl`, `snapshot_hash` and `index_version` stay as they are, and no version is bumped: `RECORD_SCHEMA_VERSION`
names the stored shape, which the caps don't change; `TOKENIZER_VERSION` and the index `SCHEMA_VERSION` cover nothing
the caps touch.
