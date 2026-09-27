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
  same cache gives the same bytes and the same hash. `backend/tests/unit/ingest/test_snapshot.py`
  builds twice from fixtures and compares the bytes.

## manifest.json
As built (`backend/src/openproceedings/ingest/snapshot.py`, `render`): `format_version`,
`record_schema_version` (`record.py`), `tokenizer_version` (dedup's title keys use it) and
`openproceedings_version`; `snapshot_hash`; `crawl_date` (the newest claim's fetch date, which also names
the directory) and `crawl_window` (the oldest and newest fetch times); `built_at` (the only build-time
value); `record_count`; `counts` nested venue → year → track → status; `abstract_missing` and
`unknown_track` per venue → year; `merges` and `conflicts` (a `total` plus a count per rule /
resolution kind); `files` (the sha256 of `merges.csv` and `conflicts.csv`, which `snapshot_hash` doesn't
cover); and `sources` — for RIS, one `ImportReport.to_manifest()` per cached file (both inputs' sha256,
the installed scholarmend `parser_version`, read / imported / skipped by reason, abstract_missing,
unknown_track, status_overrides, track × status) under `ris` (present whenever no other source is); once
`op ingest openreview` has finished a venue-year, `openreview_v2`: its own `crawl_window` (which search records'
`crawl_dates` and `/coverage` read) and one `CrawlReport.to_manifest()` per venue-year (groups crawled and skipped
with the reason, each group's `public_*` flags, notes per venueid, read / imported / skipped by reason,
unknown_track, abstract_missing, track × status, page size); likewise `openreview_v1` for API v1 years
(TASK-051: its `crawl_window`, absent when its crawls fetched nothing such as ICLR 2015 alone, and one v1
`CrawlReport.to_manifest()` per venue-year: notes per invitation, forums read, read / imported / skipped by
reason, `unmapped` status strings by evidence kind, unknown_track, unknown_status, `authors_unsplit`, the
number of conflicts, track × status and the year's `coverage_gaps`); and the proceedings crawlers
(task-052/053) add `neurips_proceedings` and `pmlr`: each `{crawl_window, listings}`, one report per listing
(venue, year, volume, listing URL, role, `stated` vs `listed` and `count_ok`, records, skipped by reason,
tracks, abstract_missing with `abstract_title_mismatch` and `page_missing`, unknown_track, `see_also`, its own
crawl window); `coverage.crawl_dates` picks up each `crawl_window`. `build` (`load_sources`) replays every
finished crawl offline through one mechanism (`sources/crawl.replay_all` over each source's `common.Crawls`:
OpenReview v2, v1, NeurIPS, PMLR, in that order; every source's reports share `common.Report`, whose fetch
times make each `crawl_window`), and adds the conflicts a v1 crawl found inside one source to
`conflicts.csv` (`with_crawl_conflicts`). The manifest may hold build times; `records.jsonl` may not. `/coverage`
(spec 04) and `coverage-auditor` read these counts directly.

## The cache
`op ingest ris <mended.ris>...` checks each scholarmend output imports cleanly, then copies it and the
`resolved.json` beside it to `<data-dir>/cache/ris/<its directory name>/`. Re-ingesting identical files is
a no-op; different files under a cached name are refused (a snapshot may already cite them).

`op ingest neurips|pmlr` fills a page cache, `<data-dir>/cache/{neurips,pmlr}/pages/<sha256[:2]>/<sha256>.json`
(one fixture-shaped entry per URL with its `fetched_at`, each written atomically; a 404 paper page is
cached as a stable absence), and writes `<data-dir>/cache/<source>/crawls/<year|vN>.json` once a listing's
pages are all cached. `op snapshot build` re-mines only marked listings, from the cache with no network; a
marked listing whose pages have gone is a refusal, never a smaller snapshot. An empty cache (no RIS and no
marked crawl) is refused.

## Immutability
- A build or ingest holds an exclusive `flock` on `<dir>/.lock` in the directory it writes into, so
  concurrent runs take turns and a sweep never touches a live run's staging directory.
- Build into a `.tmp-` directory next to the target, fsync the files and the directory (`F_FULLFSYNC` on
  macOS), rename it into place, check it holds what was written, then make it read-only (files 0444,
  directory 0555: a read-only directory can't be renamed). To delete a cache or scratch copy by hand,
  `chmod -R u+w` it first. A
  crash never leaves a half snapshot under the final name; the next build sweeps `.tmp-` leftovers, and
  a hidden or `.tmp-` cache entry is never read as a source. The cache (`op ingest ris`) is written the
  same way, all inputs or none, as the exact bytes that were checked; a cache name that differs from
  another only in case or Unicode form is refused (macOS folds both), and a symlinked input is read from
  where it points. `resolved.json`'s shape is checked, so bad input is a one-line refusal.
- If the target exists, is complete, its `records.jsonl` re-hashes to this snapshot's hash (never
  trusting the manifest) and its manifest names that hash and the current `format_version`, report it
  and exit 0 with no rewrite (`created: false`), re-locking it if a crash left it writable; otherwise
  **refuse** and say to retire it (an old-format snapshot is retired and rebuilt, never patched). A target that
  appears while building is judged the same way.
- Reading a snapshot (`load_records`, used by `diff`) requires a manifest whose `snapshot_hash` matches
  `records.jsonl`, unique ids and valid records; errors name the line and the error kind, never text.
- `.claude/hooks/protect-data-dir.sh` blocks Write/Edit under `data/snapshots/` and `data/indexes/`,
  blocks `rm`/`mv`/`truncate`/`sed -i` there, and blocks `git add -f data/`. A block is correct
  behaviour, not an obstacle. Build a new snapshot instead.
- Old snapshots are retired only through the documented prune path (`release-manager`), never deleted by
  hand while a search record references them.

## CLI
- `op [--data-dir data] snapshot build [--from <cache>] [--out <snapshots>]` imports all cached sources,
  then dedup → write. It never fetches, so it works offline, and an offline cache never expires (TASK-102),
  so the same cache rebuilds the same bytes at any date. It prints `{path, snapshot_hash, created,
  unexpected_statuses}`; `created: false` means a snapshot with that hash already existed and nothing was
  written. `unexpected_statuses` (TASK-109, `ingest/status_check.py`) lists each (venue, year, status) whose
  records hold a status none of the venue-year's claim sources can supply, with the record ids: a
  classification error to chase, never written into the snapshot.
- `op snapshot diff <a> <b>` prints (JSON) the ids **added**, **removed**, **rekeyed** (the same native
  id under a new venue or year, with the fields that differ) and **changed** (where `content_hash`
  differs, with the changed fields named), plus separate counts of **display-only** changes (`authors`,
  `urls`, `keywords`, `presentation` or `venue_id_raw` differ but the hash doesn't) and provenance-only
  changes. Every
  snapshot promotion needs one: a removed id in a stable venue-year is a regression until explained.

## Checklist
- [ ] build twice from the same cache and get byte-identical `records.jsonl`
- [ ] manifest totals equal the `records.jsonl` line count
- [ ] `op snapshot diff` against the current snapshot reviewed and attached to the PR
