# Scrubbed proceedings fixtures can't pass the miner's title check, and a volume-table row changes the RIS import

**Key lesson:** A proceedings fixture scrubbed by `scrub.py` gives the abstract page a different synthetic title from its listing entry, so a miner that (rightly) takes an abstract only when `citation_title` matches will drop every recorded abstract: test the match path on an explicitly derived page and keep the untouched page as the mismatch case; and treat any edit to the PMLR volume table as an RIS-import change, because the RIS importer, `urls.native` and the miner read the same table.

- **Date:** 2026-09-27 · **Task:** TASK-052, TASK-053 · **Area:** ingest
- **Artifacts:** `backend/src/openproceedings/ingest/sources/` (`http.py`, `neurips.py`, `pmlr.py`,
  `crawl.py`, `common.py`, `html.py`), `backend/src/openproceedings/ingest/pmlr_volumes.toml`,
  `backend/tests/unit/ingest/test_{neurips,pmlr,fetch}.py`, `test_ris.py`

## What we set out to do
Build the NeurIPS proceedings and PMLR miners (cached, polite, resumable, offline-rebuildable) and move
the ICML volume table into a verified config file, all tested only against recorded fixtures.

## What we learned
- **Scrubbing decouples titles.** `neurips/2013/abstract.json` (hash `01386bd…`) says `citation_title =
  Synthetic title 3`; the 2013 listing calls the same hash `Synthetic title 1`. The same holds for 2024 and
  PMLR v235 (`abe24a`: listing `Synthetic title 2`, page `Synthetic title 9`). Evidence:
  `test_an_abstract_is_taken_only_when_citation_title_matches`, `test_v235_page_title_mismatch_drops_the_abstract`.
- **Adding v28–v97 changes what RIS imports.** A `pmlr_url` in v97 used to be skipped (`no_id` with
  scholarmend's `pmlr_index` venue claim, else `out_of_scope`); now it is `op:icml:2019:pmlr-v97-…`
  (`test_a_pmlr_url_in_the_added_icml_volumes_now_imports_as_icml`). Adding the 2021 D&B host to
  `urls.py` likewise makes those URLs parse, so the RIS token check now uses the miner's host/year rules
  (`classify_neurips_listing`), or `round1` would have read as `unknown` and conflicted.
- **The 2025 year page links a separate main-conference volume** (`<p class="book-see-also">` →
  `/paper_files/paper/2025/vol38-main-conference`), found only by reading the recorded page. The miner
  reports it (`see_also`) and doesn't crawl it: its structure isn't recorded.
- **An offline re-mine makes snapshots a function of the cache.** `op snapshot build` re-runs the miners
  with no transport over marked listings; a cached 404 for a missing paper page keeps that rebuild
  identical to the crawl (`test_snapshot_build_includes_finished_crawls_offline`).

## Dead ends — don't repeat these
- A shell heredoc or a `sed` on a computed path is refused in a worktree-isolated agent session: edit
  files with the Edit tool, or put a script in the scratchpad and run it with a literal path.
- Asserting a crawl window against the test's fake clock fails when the crawl goes through `ingest_*`
  (it builds its own `Fetcher` with the real clock): compare the source window with the listing's.

## Decisions (and what would change them)
- NeurIPS competition volumes (v123/v133/v176/v220) are table rows but `out_of_scope`: spec 01 lists PMLR
  for ICML only and a `pmlr-` native id is ICML-only. A spec 01 + record-schema change would ingest them.
- The `Datasets_and_Benchmarks` alias applies only up to 2023; a 2024+ page using it is `unknown`.
- An ellipsis inside an abstract is kept (spec 01, record-schema); only a leading or trailing `…` is a
  snippet. The neurips-proceedings skill said "reject any `…`" and was corrected.

## Follow-ups
- [ ] Proposals in the TASK-052/053 report (record the 2025 `vol38-main-conference` page; a first live
  crawl; ingest NeurIPS competition volumes; join PMLR↔OpenReview on the v235 forum link).

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/skills/neurips-proceedings/SKILL.md`,
  `.claude/skills/pmlr-proceedings/SKILL.md`, `.claude/skills/snapshots/SKILL.md`,
  `.claude/skills/track-taxonomy/SKILL.md`, `.claude/agents/proceedings-miner.md`, `docs/specs/01-ingestion.md`,
  `CLAUDE.md` (layout)
- Test or hook added? — `backend/tests/unit/ingest/test_neurips.py`, `test_pmlr.py`, `test_fetch.py`,
  `test_ris.py` (the RIS behaviour change)
