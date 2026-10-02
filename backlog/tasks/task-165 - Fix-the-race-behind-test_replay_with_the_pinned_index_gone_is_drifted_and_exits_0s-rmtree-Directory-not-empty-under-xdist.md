---
id: TASK-165
title: >-
  Fix the race behind
  test_replay_with_the_pinned_index_gone_is_drifted_and_exits_0's rmtree
  'Directory not empty' under xdist
status: To Do
assignee: []
created_date: '2026-10-02 09:27'
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
Source: a local full-suite run on a heavily loaded machine (2026-10-02). backend/tests/contract/test_record_cli.py::test_replay_with_the_pinned_index_gone_is_drifted_and_exits_0 failed once with OSError 'Directory not empty' from shutil.rmtree(data_dir / 'indexes' / store.big) under pytest-xdist (-n auto); it passes alone and on rerun. rmtree raises that when a file appears in the directory while it is being removed, so something still writes into, or holds open, the index directory when the test deletes it. `data_dir` is a per-test copy (tests/contract/conftest.py), so another test sharing the path is unlikely. A lead to check first: search._submit runs engine.facets on the shared `op-facets` thread pool, which can outlive the `op search`/`record save` call that started it and still hold the index's reader (Tantivy may write or release files as it closes). Find the writer and remove the race. Do not add a retry or ignore_errors: a retry would hide a real concurrent write into an index.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The cause is identified and written in the task notes (which thread or process touches the index directory, and why it can overlap the rmtree)
- [ ] #2 The fix removes the overlap (for example the facets future is awaited or its reader closed before the call returns), with no retry, sleep or ignore_errors
- [ ] #3 A regression check reproduces the old failure deterministically if practical (for example by holding a reader open), or the notes say why it can't be made deterministic
- [ ] #4 The one test (or its module) passes in a loop of at least 200 runs under -n auto while the machine is under load, and the run is recorded in the notes
<!-- AC:END -->
