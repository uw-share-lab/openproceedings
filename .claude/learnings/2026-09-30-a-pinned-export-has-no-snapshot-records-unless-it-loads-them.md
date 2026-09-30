# A pinned export has no snapshot records unless it loads them: only the served bundle carries them

**Key lesson:** Per-record data computed at snapshot load (`RecordFile.attributions`) lives only on the served bundle (`Served.records`); a pinned `index_version` or record export gets a bare `TantivyEngine` from `IndexState.pinned`, so anything an export needs beyond the index's display record must come through `IndexState.pinned_records(version)` (refused with 409 when the snapshot won't verify), never be skipped silently for pinned engines.

- **Date:** 2026-09-30 · **Task:** task-138 · **Area:** api
- **Artifacts:** `backend/src/openproceedings/api/state.py` (`pinned_records`), `backend/src/openproceedings/api/export.py` (`sources_of`), `backend/tests/contract/test_export_attribution.py`

## What we set out to do
Name each exported abstract's source (decision-018) by reusing TASK-134's attribution, computed per record
when the snapshot loads.

## What we learned
- The display record the index stores (`engine/index.py`: title, abstract and `snapshot.DISPLAY`) has no
  provenance, so an export can't compute the attribution from what `TantivyEngine.documents` yields (evidence:
  `TantivyEngine._display`).
- `GET /search` only ever reads the served index, so reading `served.records.attributions` was enough there.
  `GET /export` also serves `index_version=` and `record_id=` exports from pinned engines, which
  `IndexState.pinned` opens without their snapshots (replays and diffs never needed them). Reading the served
  bundle's attributions for those would have credited abstracts from the wrong corpus, or none.
- `op export` opened only the index too; it now verifies the snapshot with `snapshot_records`, as
  `op eval coverage` and the server load do.

## Dead ends — don't repeat these
- Loading records inside `open_pinned` would add a full snapshot pass to every replay and diff; load them
  lazily, in the same one-at-a-time open slot, and remember a failure as a refused pin is remembered.
- Letting the writers default to "no attribution" when no mapping is passed hides a forgotten call site;
  `entries`/`write` take `sources` as a required keyword and a record missing from it is an internal error.

## Decisions (and what would change them)
- A pinned index whose snapshot can't be verified refuses the export (409 `API_INDEX_VERSION_UNAVAILABLE`)
  rather than sending it unattributed (decision-018). Storing the attribution in the index itself would remove
  the snapshot dependency, but changes every `index_version`.

## Follow-ups
- none

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/skills/api-contract/SKILL.md` (§Exports are contract too), spec 04 §Exports and §Implementation notes
- Test or hook added? — `backend/tests/contract/test_export_attribution.py` (pinned, record-pinned, snapshot-gone and refusal-memory cases)
