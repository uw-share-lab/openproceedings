# A Tantivy reader writes its lock file after `open` returns, and a "not reproduced" Unicode split hid behind a backslash

**Key lesson:** A tantivy-py `Index.open` starts a meta.json watcher thread whose first poll reloads the reader and re-creates `.tantivy-meta.lock` after `open` has returned. Never `rmtree` an index directory right after an in-process open. Take it away by an atomic rename instead, and open built indexes with `config_reader(reload_policy="manual")`. When checking a normalizer for Unicode-form splits, include LaTeX and markup characters in the generator (a `\` before a letter), not only letters and marks.

- **Date:** 2026-10-02 · **Task:** TASK-165, TASK-168 (with TASK-162, TASK-163) · **Area:** engine
- **Artifacts:** `backend/src/openproceedings/engine/index.py` (`open_index`), `backend/tests/contract/test_record_cli.py` (`take_away`), `backend/src/openproceedings/ingest/dedup.py` (`title_key`), `backend/tests/unit/ingest/test_dedup.py`, the TASK-165 and TASK-168 notes, decision-031

## What we set out to do

Find the writer behind a flaky `rmtree` "Directory not empty" under xdist, and reproduce (or rule out) the dedup-auditor's NFC-vs-NFD title-key split.

## What we learned

- **The writer is Tantivy itself, not our code.**
  - tantivy-py's `Index.open` builds a default (OnCommitWithDelay) reader. Its meta.json watcher thread polls once at start and reloads.
  - The reload takes META_LOCK, which creates `.tantivy-meta.lock`.
  - Evidence (a scratch probe: open, delete the lock, watch for it): on 190 of 200 opens the lock reappeared 0.1–54 ms after `open` returned. With an immediate `config_reader(reload_policy="manual")` it reappeared on 12 of 200, all within 9 ms. After `del` of the index it never reappeared.
  - The engine was already freed when the test removed the directory, so the late write came from the watcher's own reload.
- **A meta.json content change triggers no reload** in tantivy 0.26, so a test built on "change meta.json and expect a reload" proves nothing. We kept a spy test of the `config_reader` call instead; the race itself can't be observed from Python.
- **The NFC/NFD split was real, but only with a backslash.**
  - `normalize` reads LaTeX on the raw text before its per-character NFKC. So an NFD `\` + `e` + U+0301 starts the command `\e`: `Caf\é` keyed `caf e` in NFC but `caf` in NFD. `Erd\H{ő}s` keyed `erdos` in NFC but `erd o s` in NFD.
  - Searches with no backslash in the generator found 0 splits: 68,116 exhaustive cases, 300k mark sequences, 60k titles. With backslashes, 2,633 of 3,000 titles split.
  - The earlier "not reproduced" verdict came from the generator's alphabet, not from the code.

## Dead ends — don't repeat these

- Looking for the writer among our own threads (the facets pool, `threading.enumerate()`): Tantivy's threads are Rust threads, invisible to Python.
- Looking for a tantivy-py way to open without a watcher: there is none. `config_reader` replaces the reader only after the watcher has started.

## Decisions (and what would change them)

- Built indexes are read with a manual reload policy, because they are immutable. A tantivy-py open option that never starts the watcher would close the remaining 12-in-200 window.
- Dedup keys are NFC-first (decision-031). Tokenizer 2's `normalize` is form-dependent before NFKC. Tokenizer 3 applies whole-string NFKC before LaTeX; the version bump and compatibility work belong to the tokenizer branch (fix/tokenizer-nfc-form).

## Follow-ups

- [x] Token contract NFKC before LaTeX: owned by the tokfix branch (fix/tokenizer-nfc-form), not this one.

## Propagated to

- Skill / agent / CLAUDE.md updated? — `.claude/skills/tantivy-indexing/SKILL.md` (manual reload; rename, never `rmtree`), `.claude/skills/dedup-rules/SKILL.md` (NFC key), spec 01
- Test or hook added? — `test_an_opened_index_is_read_with_a_manual_reload_policy` and `test_a_build_reads_its_index_with_a_manual_reload_policy` (`backend/tests/unit/engine/test_index.py`); `test_every_canonically_equivalent_title_has_one_key` (`backend/tests/unit/ingest/test_dedup.py`)

## Addendum — 2026-10-02

The takedown checker must collect twin links from every loaded snapshot independently of its preferred title/authors record. A served record with no links masked an older pinned record's links because the metadata fallback only read that record when the served ID was absent. Keep the fallback for title queries, and separately union served and pinned twin links. Evidence: `test_twin_links_from_every_pinned_version_survive_served_empty_links` in `backend/tests/unit/test_takedown_check.py` covers an older linked snapshot and distinct links across multiple pinned versions, including repeated links.

Propagated to spec 08's `op takedown check` contract and the regression tests; no follow-up remains for this checker finding.

## Addendum — 2026-10-02: Linux visual baselines come from the Linux runner

PR #92's first Linux Playwright run (37089484805) passed all 17 functional/accessibility tests and failed only the two visual snapshots, whose Linux baselines still predated the twin fixture. The Darwin baselines and all 19 local E2E tests had already passed. Inspect the CI actual and diff before accepting a platform baseline: both themes showed the intended “See also” rows under the first two hits, adding 30 px each (1440 × 12175 → 1440 × 12235), and the fixture's changed index hash. The filters sidebar stayed in place; the remaining results aligned after the 60 px shift. Copy only those two verified CI actual images into the Linux baselines, then rerun E2E and CI with unchanged screenshot dimensions and tolerances. The artifact, diff, failure log and inspection crops are preserved under `/tmp/twins-pr92-playwright-artifact/` and `/tmp/twins-pr92-*-top.png`.

## Addendum — 2026-10-03: corrupt mapped files without truncation

PR 94 CI crashed with SIGBUS inside pathlib.write_bytes in the changed-index refusal test. The intended append first opened the live Tantivy store with wb, truncating its inode to zero. An isolated Linux live-mmap reproducer deterministically exited with signal 7; the actual Tantivy fixture had a mapped store, while one diagnostic corruption attempt did not crash (the native-reader race is timing-dependent). This is a fixture mutation hazard, not evidence that production hash verification passed corrupted data. Index files are sealed read-only, and verification hashes them before opening Tantivy.

The test now appends the same byte with ab and asserts unchanged inode, expected length and exact corrupted bytes before retaining both verification and rebuild refusal assertions. The complete focused index suite passed on Linux (42 tests) and macOS (42 tests). Disabling the actual hash comparison in an isolated copy made the corruption test fail when Tantivy tried to open the damaged store, proving the refusal check remains meaningful. Production code was restored and is unchanged. Raw diagnostics: /tmp/hooks-index-sigbus-diagnostic.log, /tmp/hooks-index-linux-negative.log; focused checks: /tmp/hooks-index-linux-green.log and /tmp/hooks-index-mac-green.log. No skip, retry or assertion weakening was introduced. Propagated to backend/tests/unit/engine/test_index.py.
