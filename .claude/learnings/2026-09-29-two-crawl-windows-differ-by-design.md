# A source's fetch window and its claim window differ by design, so an equality check refused the first real snapshot

**Key lesson:** When a manifest records the same idea twice from different evidence (every response fetched, or only the claims on records), define which one each consumer reads. Don't assert they're equal: a check that holds on small fixtures can fail on the first real crawl. Run the whole pipeline on real data (snapshot → index → report → serve) before depending on it.

- **Date:** 2026-09-29 · **Task:** task-122 · **Area:** api
- **Artifacts:** `backend/src/openproceedings/coverage.py` (`crawl_dates`), `backend/src/openproceedings/records.py` (`snapshot_facts`), `backend/tests/unit/test_coverage.py::test_a_claim_window_narrower_than_the_fetch_window_is_served_and_wins`, `backend/tests/unit/test_records.py::test_a_claim_window_narrower_than_the_fetch_window_saves_a_record_like_coverage`

## What we set out to do
Trial TASK-054 part 2 (snapshot, index, `op eval coverage`) on the 2026-09-29 live crawl before the last listing finished.

## What we learned
- The snapshot (96,601 records) and its index built fine. `op eval coverage` then refused with "the snapshot manifest gives a source two crawl windows" (evidence: the trial run in a scratch data directory, snapshot `f2ba9c975ae4`, index `2615ff379520`).
- openreview_v2's `sources[].crawl_window` began at 06:09:01Z (the first `/groups` call) and its `crawl_windows` entry at 06:10:05Z (the first note that made a record). Both are right; they measure different things.
- The API computes coverage when it loads an index, and a search record's `snapshot_facts` duplicated the same check. So the real index could not have been served, nor a search saved on it. The recorded fixtures never showed it, because a small crawl's first and last responses both make records.
- Once fixed, the same trial gave the first real M4 verdict: 35 of 44 gated cells within ±1%.

## Dead ends — don't repeat these
- An existing refusal-table row ("two windows for `ris`") encoded the bug as intended behaviour, so the tests defended it. Where a refusal row describes something real data can produce, ask what the data means before keeping it.

## Decisions (and what would change them)
- Per source, the claim window (`crawl_windows`, spec 04) wins; the fetch window is used only when a source has no claim window (format 1). A source named `*` is still refused, now by both functions alike.

## Follow-ups
- [ ] task-054 — classify the 9 failing cells from the trial once the NeurIPS 2025 listing is complete.

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/skills/snapshots/SKILL.md` (which window `crawl_dates` uses), `docs/specs/04-backend-api.md` (the record's `crawl_dates`)
- Test or hook added? — the two tests above; the old refusal row was removed
