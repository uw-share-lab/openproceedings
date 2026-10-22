# List counts and native-id lengths, and what decision-054's and decision-055's bounds change (TASK-280, TASK-281)

2026-10-22 · TASK-280 · TASK-281 · decision-054 · decision-055 · read-only over the maintainer's snapshot; no
snapshot or index was built, moved or deleted.

decision-054 caps how many authors (500) and keywords (200) a record keeps, trimmed and flagged. decision-055 bounds
the native part of every record id: a PMLR or dblp key of at most 200 characters, an OJS article id, a PMLR volume and
each side of an ACM DOI's `<toc>.<n>` of at most 12 digits, and a record past a bound is refused. Both were checked
against the current corpus before they were adopted.

| | |
|---|---|
| Snapshot | `2026-10-16-03eab0ef56c4` (`snapshot_hash` `03eab0ef56c4d768ca25c1942207d1c9eaf14a1d852bd276a05e013ae17210c7`), 173,518 records, built at record schema 9, tokenizer 3 |
| Script | [`2026-10-22-list-counts-and-native-ids-check.py`](2026-10-22-list-counts-and-native-ids-check.py): `uv run python docs/results/2026-10-22-list-counts-and-native-ids-check.py <snapshot>`, from the main checkout (where `data/` lives) or with the snapshot's absolute path (about 110 s) |
| Code | the TASK-280/281 branch (`feat/ingest-count-and-id-bounds`), record schema 10 |
| Counted | every record and every claim, losing claims included |

## How many authors and keywords

| List | Most on a record | Most on a claim | Cap | Ratio |
|---|---|---|---|---|
| authors | 95 | 95 | 500 | 5.3× |
| keywords | 54 | 54 | 200 | 3.7× |

## The longest native id of each form

| Part | Longest | Bound | Ratio |
|---|---|---|---|
| a dblp key (`dblp-<key>`, ICML and AAAI) | 30 | 200 characters | 6.7× |
| a PMLR key (`pmlr-v<N>-<key>`) | 25 | 200 characters | 8× |
| a PMLR volume (`<N>`) | 3 digits | 12 digits | |
| an OJS article id (`ojs-<id>`) | 5 digits | 12 digits | |
| an ACM DOI's toc (`doi-<toc>.<n>`) | 7 digits | 12 digits | |
| an ACM DOI's paper number | 7 digits | 12 digits | |
| the whole id | 53 characters | (the forms bound it: at most 233, a FAccT `pmlr-` id) | |

The NeurIPS and ICLR forms (`nips-`/`iclr-<32 hex>`) and OpenReview forum ids (4–64 characters) were bounded before.

## What the bounds change

Every line of `records.jsonl` validates as a `PaperRecord` under record schema 10 (`iter_records` validates each, and
would stop at the first id past a bound), and `cap_record` with decision-054's list caps returns every record
unchanged: `records=173518 valid=173518 changed=0 flagged=26`. The 26 flagged are the records decision-026 already
trimmed (the manifest's `trimmed`).

So `records.jsonl`, `snapshot_hash` and `index_version` stay as they are. The record schema version goes from 9 to 10
because the native-id forms changed (record-schema skill §Versions), which changes the next snapshot's manifest
(`record_schema_version`) but no record; the index `SCHEMA_VERSION` and `TOKENIZER_VERSION` cover neither change.
