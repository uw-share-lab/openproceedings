---
id: TASK-165
title: >-
  Fix the race behind
  test_replay_with_the_pinned_index_gone_is_drifted_and_exits_0's rmtree
  'Directory not empty' under xdist
status: Done
assignee: []
created_date: '2026-10-02 09:27'
updated_date: '2026-10-03 02:13'
labels:
  - tests
  - bug
  - records
dependencies: []
references:
  - backend/tests/contract/test_record_cli.py
  - backend/src/openproceedings/search.py
priority: medium
ordinal: 135000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Source: a local full-suite run on a heavily loaded machine (2026-10-02). backend/tests/contract/test_record_cli.py::test_replay_with_the_pinned_index_gone_is_drifted_and_exits_0 failed once with OSError 'Directory not empty' from shutil.rmtree(data_dir / 'indexes' / store.big) under pytest-xdist (-n auto); it passes alone and on rerun. On POSIX, rmtree raises that only when a file is created inside the directory while it is being removed, so something writes into indexes/<big> during the rmtree. `data_dir` is a per-test copy (tests/contract/conftest.py), so another test sharing the path is unlikely. `record save` runs search with facets off, and search.run waits for (or, on an exception, cancels) its facets future, so the op-facets pool can outlive only a search that raised. Leads to check: a file Tantivy writes when an index is opened or a reader is reloaded (a lock or meta file), and any background work left from the test's earlier `op` calls. Find the writer and remove the race. Do not add a retry or ignore_errors: a retry would hide a real concurrent write into an index.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The cause is identified and written in the task notes (which thread or process touches the index directory, and why it can overlap the rmtree)
- [x] #2 The fix removes the overlap (for example the facets future is awaited or its reader closed before the call returns), with no retry, sleep or ignore_errors
- [x] #3 A regression check reproduces the old failure deterministically if practical (for example by holding a reader open), or the notes say why it can't be made deterministic
- [x] #4 The one test (or its module) passes in a loop of at least 200 runs under -n auto while the machine is under load, and the run is recorded in the notes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Identify Tantivy watcher writes; configure manual readers and atomically rename removed indexes in tests; pin reader configuration and verify 200 repeats under load.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Cause (2026-10-02): the writer is tantivy's meta.json watcher thread, which tantivy-py's Index.open starts with the default (OnCommitWithDelay) reader. Its first poll reloads the reader, and the reload takes META_LOCK, creating .tantivy-meta.lock again. That reload runs on its own thread holding its own Arc on the reader, so it can land after open returns and even after the Python engine is dropped. In test_replay_with_the_pinned_index_gone_is_drifted_and_exits_0 the in-process 'op record save' opens indexes/<big> (verify_index's throwaway open plus the engine's), and under load the watcher's reload lands inside shutil.rmtree, which then fails with ENOTEMPTY. Measured on the test index: 190 of 200 opens re-created the lock after open returned (0.1-54 ms later). After a del, none. A meta.json content change triggers no reload (tantivy 0.26). The facets pool is not involved.
Fix: engine/index.py open_index calls index.config_reader(reload_policy='manual') at once (indexes are immutable; nothing needs a reload), and build_index does the same (it already reloads explicitly). This brings it to 12 of 200, all within 9 ms: only a first poll that beats config_reader can still reload, and tantivy-py offers no way to open without the watcher, so that window can't be closed from Python. So the three test_record_cli tests that removed an index right after an op call now take it away with an atomic rename out of the data dir (take_away). A late lock write lands in the moved directory, so there is no overlap at all. No retry, sleep or ignore_errors.
Regression check: test_an_opened_index_is_read_with_a_manual_reload_policy pins the config_reader call. The race itself can't be made deterministic (the watcher is a Rust thread whose timing Python can't observe); the 190/200 vs 12/200 measurement is the evidence.
Loop: the test, parametrized 200x, run with -n auto while other agents' suites were running (load average 117 -> 151): 200 passed in 27.2 s.

Final integration cdb68cdb6fc12bd0ae9c23bed1788e1fd1c78511 on merged dev9152ecb: make test PASS6386backend/2optional skips and3217frontend; make lint/tooling PASS; make e2e PASS19. Fresh focused index/dedup/twins/checker/takedown tests PASS289. Logs /tmp/twins-finalization-{test,lint,tooling,e2e,focused}.log. Independent integrated all-role review APPROVE /tmp/twins-integrated-all-role-review.md. Final metadata commit and its fresh fulltest/lint/tooling remain required before publication.

Fresh final race proof: /tmp/twins_race_repeat.py adds200function-scoped fixture repetitions of the exact pinned-index-gone test. uv run --locked pytest ... -p twins_race_repeat -q -n auto with PYTEST_XDIST_AUTO_NUM_WORKERS=4 passed200in7.06s. Two explicit CPU burners ran concurrently under shared heavy lock; uptime load8.83/9.99/12.13 before and10.12/10.22/12.19 after. Logs /tmp/twins-finalization-race.log and race-load.log.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Identified Tantivy meta watcher recreating its reader lock. Manual reader configuration reduces watcher activity; atomic rename prevents removal overlap without retries, sleeps or ignore_errors. Fresh200-repetition exact regression with4xdist workers passed7.06s under two CPU burners, load8.83→10.12; full suite also passed.
<!-- SECTION:FINAL_SUMMARY:END -->
