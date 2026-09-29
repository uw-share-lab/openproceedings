# A NeurIPS proceedings hash is not a paper id on the 2021 D&B host

**Key lesson:** Before trusting a URL component as a native id, check it on the live listing for collisions between different titles. The NeurIPS path hash is md5 of a per-site paper number, so the 2021 D&B host reuses hashes across round 1, round 2 and the main track. A listing whose `count_ok` is true can still lose papers at the id dedup step, so read `skipped.duplicate` too.

- **Date:** 2026-09-29 · **Task:** task-118 · **Area:** ingest
- **Artifacts:** `backend/src/openproceedings/ingest/urls.py` (`proceedings_native`), `backend/src/openproceedings/ingest/sources/neurips.py`, `backend/src/openproceedings/ingest/ris.py`, `backend/tests/unit/ingest/test_urls.py`, `backend/tests/unit/ingest/test_neurips.py::test_2021_db_papers_sharing_a_hash_are_all_kept`

## What we set out to do
Run the first live dry-run crawls for the M4 coverage gate (TASK-054) and compare each listing with its official count.

## What we learned
- Every NeurIPS listing matched its official count except 2021 D&B. It listed 174 (official 174), but only 120 were planned: `skipped: {"duplicate": 54}` (evidence: `op ingest neurips --year 2013-2025 --dry-run`, 2026-09-29).
- None of the 54 were real duplicates. 27 hashes appear in both round 1 and round 2 of the D&B page, and 27 are shared with 2021 main-track papers. 0 of 54 share a title (evidence: title comparison over the cached D&B and main 2021 index pages).
- The hash is `md5(str(n))` for a paper number n. The first D&B entry's hash is md5 of `138`. The main proceedings site never reuses a number (no other year had a duplicate), but the D&B site numbers each round from 1 on its own.
- `count_ok` compares listed entries with the page's stated count before any id exists. So it passes while the id dedup step drops a third of the cell, and the loss shows only in `skipped.duplicate`.
- The same bug was in `urls.native()`. A RIS row citing a D&B URL would have taken an unrelated main-track paper's id, and dedup would then have merged the two.

## Dead ends — don't repeat these
- The recorded D&B fixture is scrubbed down to 4 entries with distinct hashes, so no fixture test could see the collision. Scrubbed fixtures keep structure, not the real id distribution. For id questions, check the live page (a dry run fetches only index pages).
- `op ingest … --dry-run --offline` is refused: a dry run always reads the live index pages. To re-read a dry run, save its JSON the first time.

## Decisions (and what would change them)
- On the D&B host only, the native id is `nips-<hash>-round1|round2`. Main-track and 2022+ ids are unchanged, so no existing id moves. A D&B link without a round gets no id (`no_round` in the miner, `unresolved` in RIS) rather than a guessed one. This would need revisiting if the D&B host ever lists another year (the classifier already sends any non-2021 D&B year to `unknown`).
- One function, `urls.proceedings_native`, builds the id for the miner, the RIS importer and dedup, and the record pattern accepts exactly its output. So an id rule can't drift between the paths again.

## Follow-ups
- [ ] task-054 — the coverage report checks `skipped.duplicate` for every listing, not just `count_ok`.

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/skills/neurips-proceedings/SKILL.md` (hash semantics, the round-qualified id, watch `skipped.duplicate`), `.claude/skills/record-schema/SKILL.md` (native-id table), `docs/specs/01-ingestion.md` (§Record schema `id`)
- Test or hook added? — `backend/tests/unit/ingest/test_urls.py` (URL → id and the record pattern), `test_neurips.py::test_2021_db_papers_sharing_a_hash_are_all_kept`, `test_ris.py::test_one_hash_on_the_main_and_db_hosts_is_two_papers_so_ambiguous`
