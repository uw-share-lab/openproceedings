# A tool that writes local time may keep epoch times elsewhere

**Key lesson:** Before marking a zone-less timestamp "offset unknown", look for the producing tool's own records (app data, query files) that store the same event in epoch seconds; one exact match fixes the offset without guessing.

- **Date:** 2026-10-01 · **Task:** task-077 · **Area:** ingest
- **Artifacts:** `backend/src/openproceedings/ingest/ris_offsets.toml`, `backend/src/openproceedings/ingest/ris.py` (`load_offsets`, `import_ris`), `backend/src/openproceedings/ingest/snapshot.py` (`query_dates`), `backend/src/openproceedings/vocab.py` (`window_kind`), decision-025

## What we set out to do
Record the time-zone offset of Publish or Perish's `M1  - Query date:` lines (local wall time, no zone), which
the RIS importer stored labelled UTC, or else mark those dates local.

## What we learned
- The cached inputs can't give the offset: `mended.ris` has only the zone-less query date, and scholarmend's
  `resolved.json` carries no timestamps (checked over both cache entries).
- PoP's own query records hold each query's run time in epoch seconds. For each search, one of them matches a RIS
  query date to the second at −04:00 (epoch 1789826585 = 2026-09-19T14:03:05Z vs `2026-09-19 10:03:05`; epoch
  1790180170 = 2026-09-23T16:16:10Z vs `2026-09-23 12:16:10`). File creation times only bracket the offset;
  the epoch match fixes it.
- `fetched_at` is outside `content_hash` but inside `records.jsonl`, so the conversion changes `snapshot_hash`
  and `index_version` on rebuild. Old search records then replay `drifted` while membership-identical. That
  belongs in the decision record, not as a surprise for whoever rebuilds.
- `crawl_dates_kind` is an open set (decision-009). Adding `_utc` kinds, and keeping the old values' local
  meaning, keeps every stored record correct with no body-version bump.
- `ingest_ris` checks each file in a random temporary directory. Any per-entry lookup has to be passed the
  cache entry's name (`cache_entry=`); otherwise the check runs under the temporary name and silently misses
  the table. A test now asserts the report's offset.

## Dead ends — don't repeat these
- Inferring the zone from the machine's current zone, or from the commit offsets on later days, is a guess
  about the day of the search; only a record written at search time counts.

## Decisions (and what would change them)
- Offsets live in a committed table keyed by cache entry, not in `data/` (decision-025): cache entries are
  immutable, and a replay must not depend on an uncommitted file. PoP writing a zone itself would retire the
  table.

## Follow-ups
- None in the backlog. The owner rebuilds the snapshot after merge (decision-025 §Consequences).

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/skills/snapshots/SKILL.md` (`query_dates`), `.claude/skills/search-records/SKILL.md`, `.claude/skills/prisma-reporting/SKILL.md`, `.claude/agents/ris-importer.md` (a new PoP search needs a table row), `CLAUDE.md` layout.
- Test or hook added? — `test_ris.py` (conversion, unlisted entry, table loader), `test_snapshot.py` (`query_dates`, the `cache_entry` check), `test_records.py` (`window_kind`, the record and `/coverage` derivations agree).
