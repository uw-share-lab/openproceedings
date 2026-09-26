---
name: snapshots
description: The corpus snapshot standard — the immutable data/snapshots/<date>-<shorthash>/ layout, records.jsonl and manifest.json contents, the determinism rules that make the same inputs give byte-identical output, how snapshot_hash feeds index_version, op snapshot build/diff semantics, and the protect-data-dir.sh hook. Use when writing or reviewing backend/src/openproceedings/ingest/snapshot.py, building or comparing snapshots, or when a hook blocks a write under data/.
---

# Snapshots (spec 01 §Pipeline 5, spec 03 §Versioning)

A snapshot is the **only** input to the index build. Its hash is folded into `index_version`
(`sha256(snapshot_hash, TOKENIZER_VERSION, SCHEMA_VERSION, ranking_params)[:12]`, spec 03). So a snapshot
that changes after the fact would break every search record that cites it (guarantee 4).

## Layout
```
data/snapshots/<YYYY-MM-DD>-<shorthash>/
  records.jsonl     # one PaperRecord per line, sorted by id
  manifest.json
  merges.csv        # .claude/skills/dedup-rules/SKILL.md
  conflicts.csv
```
`data/` is gitignored and **never committed**, because corpus licensing is unresolved (spec 00 §Open
questions 1).

## records.jsonl: determinism rules
- Sort by `id` using plain code-point order.
- One line per record: `json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`,
  followed by `\n`, UTF-8, with no BOM.
- Sort lists with no natural order: `provenance` by `Claim.sort_key()`, which is `(field, source, url or "",
  fetched_at)` (a missing url sorts first); `PaperRecord` enforces this order on load. Keep `authors` in display
  order.
- Take `fetched_at` from the cache entry, **not** the build clock. Take no values from the environment
  (hostname, cwd, locale).
- `snapshot_hash = sha256(records.jsonl bytes)`, and `<shorthash>` is a fixed-length prefix of it. The
  same cache gives the same bytes and the same hash. `backend/tests/unit/ingest/test_snapshot_determinism.py`
  builds twice from fixtures and compares the bytes.

## manifest.json
As built (`backend/src/openproceedings/ingest/snapshot.py`, `render`): `snapshot_hash`; `crawl_date` (the
newest claim's fetch date, which also names the directory); `built_at` (the only build-time value);
`record_count`; `counts` nested venue → year → track → status; `abstract_missing` and `unknown_track`
per venue → year; `merges` and `conflicts` (a `total` plus a count per rule / resolution kind); and
`sources` — for RIS, one `ImportReport.to_manifest()` per cached file (both inputs' sha256, the
scholarmend version, read / imported / skipped by reason, abstract_missing, unknown_track,
status_overrides, track × status). The crawlers add their own source entries (crawl window, API host
and version, page counts) in M4. The manifest may hold build times; `records.jsonl` may not. `/coverage`
(spec 04) and `coverage-auditor` read these counts directly.

## The cache
`op ingest ris <mended.ris>...` checks each scholarmend output imports cleanly, then copies it and the
`resolved.json` beside it to `<data-dir>/cache/ris/<its directory name>/`. Re-ingesting identical files is
a no-op; different files under a cached name are refused (a snapshot may already cite them).

## Immutability
- Build into a temporary directory next to the target and `os.replace` it into place. A crash never
  leaves a half snapshot under the final name.
- If the target already exists, **refuse**. If a snapshot with the same `snapshot_hash` already exists,
  report it and exit 0 with no rewrite.
- `.claude/hooks/protect-data-dir.sh` blocks Write/Edit under `data/snapshots/` and `data/indexes/`,
  blocks `rm`/`mv`/`truncate`/`sed -i` there, and blocks `git add -f data/`. A block is correct
  behaviour, not an obstacle. Build a new snapshot instead.
- Old snapshots are retired only through the documented prune path (`release-manager`), never deleted by
  hand while a search record references them.

## CLI
- `op [--data-dir data] snapshot build [--from <cache>] [--out <snapshots>]` imports all cached sources,
  then dedup → write. It never fetches, so it works offline. It prints `{path, snapshot_hash, created}`;
  `created: false` means a snapshot with that hash already existed and nothing was written.
- `op snapshot diff <a> <b>` prints (JSON) the ids **added**, **removed** and **changed** (where `content_hash`
  differs, with the changed fields named), plus separate counts of **display-only** changes (`authors`,
  `urls`, `keywords`, `presentation` or `venue_id_raw` differ but the hash doesn't) and provenance-only
  changes. Every
  snapshot promotion needs one: a removed id in a stable venue-year is a regression until explained.

## Checklist
- [ ] build twice from the same cache and get byte-identical `records.jsonl`
- [ ] manifest totals equal the `records.jsonl` line count
- [ ] `op snapshot diff` against the current snapshot reviewed and attached to the PR
