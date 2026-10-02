# A cached verified clause still cost its whole id list on every search

**Key lesson:** A memoised Tantivy query is not memoised work: Tantivy resolves a term set's terms on every search, so a filter of N ids costs ~0.5 µs × N per search; when the ids are most of a known superset, name the few that fail as a `MUST_NOT` instead, which matches and scores identically.

- **Date:** 2026-10-02 · **Task:** TASK-076 · **Area:** engine
- **Artifacts:** `backend/src/openproceedings/engine/compile.py` (`Compiler.exact`, `id_set`),
  `backend/tests/unit/engine/test_verified_exclusion.py`, `backend/tests/bench/warm_verified.py`,
  `backend/tests/bench/report_80k.py` (warm p99), `docs/results/2026-10-02-wildcard-phrases.md`,
  `docs/results/2026-10-02-bench.md`.

## What we set out to do
Headroom for `main-2-pop`'s warm search (wildcard phrases, every clause verified and cached): p95 under 50 ms
and p99 under 100 ms at 80k.

## What we learned
- The compiled query was already memoised per tree (M2 gate), yet a warm search was 25–45 ms. Timing the
  query's parts with `searcher.search(q, 1, count=True)` showed the id term sets alone at about 0.5 µs an id:
  10.7 ms of 24.5 ms for one 20,752-id clause (synthetic), 15.1 ms for 11,378 ids (real) (evidence:
  `docs/results/2026-10-02-wildcard-phrases.md` §Where a warm search went).
- A verified clause's ids are a subset of its candidates, so `candidates AND NOT failed` is exactly the ids,
  and since the old id set was a constant-0 score, both forms give the same float scores (the
  `test_verified_exclusion` property over every `engine_asts` tree, with and without the form). On the real
  corpus most candidates of `"large language model$"` hold it: `main-2-pop` p95 46.8 → 27.3 ms.
- task-031's 95/148 ms probe was load: on a quiet machine the old code already read p95 28 ms on the synthetic
  corpus. A wall p99 far above the CPU p99 is preemption; report both.

## Dead ends — don't repeat these
- Reading the synthetic corpus alone would have shown no gain: its big clause has more failures than passes.
  Measure the real corpus too before deciding a change doesn't help.

## Decisions (and what would change them)
- Choose the shorter list per clause (count from the index, one candidate collection at compile only when the
  failures are fewer). A tantivy-py API for a reusable doc set, or an indexed per-document ord, would remove
  the per-search cost entirely; neither is needed for the budget today.

## Follow-ups
- [ ] none (the remaining per-search cost of a clause whose lists are both long is recorded in the results doc)

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/skills/ast-compilation/SKILL.md` (the verified row), spec 03
  (`Near` row and a Measured bullet), `compile.py`'s module table.
- Test or hook added? — `backend/tests/unit/engine/test_verified_exclusion.py`.
