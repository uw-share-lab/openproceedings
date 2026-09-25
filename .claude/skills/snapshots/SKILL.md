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
- Sort lists with no natural order (`provenance` by `(field, source, url)`). Keep `authors` in display
  order.
- Take `fetched_at` from the cache entry, **not** the build clock. Take no values from the environment
  (hostname, cwd, locale).
- `snapshot_hash = sha256(records.jsonl bytes)`, and `<shorthash>` is a fixed-length prefix of it. The
  same cache gives the same bytes and the same hash. `backend/tests/unit/ingest/test_snapshot_determinism.py`
  builds twice from fixtures and compares the bytes.

## manifest.json
Includes: `snapshot_hash`; `crawl_date`; `built_at`; `record_count`; `counts` nested venue → year →
track → status; `abstract_missing` per venue-year; `unknown_track` per venue-year; `merges` and
`conflicts` totals; and `sources` (for each source, the crawl window, API host and version, and the
PMLR/NeurIPS page counts). The manifest may hold build times; `records.jsonl` may not. `/coverage`
(spec 04) and `coverage-auditor` read these counts directly.

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
- `op snapshot build [--from <cache>]` merges all cached sources, then classify → dedup → write. It never
  fetches, so it works offline.
- `op snapshot diff <a> <b>` prints the ids **added**, **removed** and **changed** (where `content_hash`
  differs, with the changed fields named), plus a separate count of provenance-only changes. Every
  snapshot promotion needs one: a removed id in a stable venue-year is a regression until explained.

## Checklist
- [ ] build twice from the same cache and get byte-identical `records.jsonl`
- [ ] manifest totals equal the `records.jsonl` line count
- [ ] `op snapshot diff` against the current snapshot reviewed and attached to the PR
