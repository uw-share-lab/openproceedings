---
id: TASK-085
title: op index retire refuses while search records pin the version
status: In Progress
assignee:
  - '@jeevanp03'
created_date: '2026-09-27 08:44'
updated_date: '2026-09-30 03:02'
labels:
  - cli
  - records
  - ops
dependencies: []
ordinal: 83000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Spec 08 lists `op index retire <index_version>` (planned, task-065): it must refuse while any search record pins the version, since a deleted pinned index turns those records into permanent drifted. openproceedings.records.RecordStore(<data-dir>/records).pinned(index_version) returns the count (task-037).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 op index retire refuses (non-zero exit, count reported, no files touched) when RecordStore.pinned(v) > 0
- [x] #2 Retires as before when no record pins v; test both
- [x] #3 release-manager agent and index-versioning skill updated
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented op index retire <index_version> [--dry-run] in cli.py (_index_retire), independent of the parked TASK-065 (the stub's planned-in link removed). Refusals (exit 1, one stderr line, nothing touched): name not matching engine.index.VERSION_NAME (checked before any path is built: ../x, current, a/b, uppercase, .tmp- names), no real directory directly under indexes/ (a symlink named like a version is not an index), current or any other symlink in indexes/ pointing at it, an unreadable record store (sqlite3.Error: never guess unpinned), RecordStore(<data-dir>/records).pinned(v) > 0 (count reported). Deletion runs the checks again under storage.exclusive(indexes) (the lock op index build holds), sweeps .tmp- leftovers, renames the dir to .tmp-retire-<v> and removes it. One log line: index_retired / index_retire_checked (dry run) / index_retire_refused (WARNING; DEBUG and no version for a malformed name), with index_version, pinned and outcome/reason. Known limit, documented: it can't see an op serve --index <v> serving the version by name. Tests: backend/tests/contract/test_index_retire_cli.py (15 cases incl. pinned count and singular, current, alias, malformed ids incl. ../x, unreadable store, retire success with other versions intact, dry run, replay on a kept version still reproduced, sweep of a leftover, help text). Docs: spec 08 §CLI row and §Deploy (refresh + takedown paragraph), spec 04 §Search records, index-versioning and logging-standards skills, release-manager and search-records-keeper agents. Full backend suite: 5519 passed, 1 failed (hypothesis DeadlineExceeded in golden/test_reference_200.py under xdist load; passes alone, untouched by this diff); make lint and make tooling green.

Review round 1 (all six Shoulds and both requested nits): after the rename, retire checks the pins and every symlink's readlink target again and renames back on a hit (race tests monkeypatch a pin and a symlink between the checks); the remaining window (a few syscalls before removal) is documented. OSError from the record store is refused as records_unreadable. A failed chmod after the rename reports tmp_left instead of raising; storage.sweep logs tmp_sweep_failed and carries on rather than failing later builds. storage.exclusive takes an on_wait callback, and retire prints that it is waiting for the lock. Symlink re-check (lstat) just before the rename. Docs: repoint, SIGHUP, confirm /api/v1/meta, then retire (release-manager, index-versioning, spec 08); release-manager retention greps docs/results and data/embeddings first. TASK-065 AC#2 reworded. Full suite 5547 passed; make lint and make tooling green.
<!-- SECTION:NOTES:END -->
