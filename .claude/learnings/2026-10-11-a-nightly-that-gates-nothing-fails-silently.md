# A nightly that gates nothing fails silently: measure growth, not seconds, and give every shard a stop

**Key lesson:** A linear-time test should compare CPU time at N and 4N, not a wall-clock bound at one size. A mutation runner should stop at a mutant's first failing table and treat a hung table as killed. Read the nightly's history before a release, because no merge waits on it and three red nights went unnoticed.

- **Date:** 2026-10-11 · **Task:** v0.3.0 release readiness (spec 08 §Release step 1) · **Area:** tests, ci, tooling
- **Artifacts:** `backend/tests/timing.py`, `backend/tests/strategies.py` (`_join`), `.claude/scripts/mutate.py`,
  `.claude/scripts/tests/test-mutate-run.sh`, `.github/workflows/nightly.yml`

## What we set out to do
Get a green nightly on the exact `dev` head for the v0.3.0 release. No scheduled nightly had passed since 2026-10-07.

## What we learned
- **Wall-clock bounds at one size flake on shared runners.** A 17 ms parse took 1.9 s and a 5 ms ICML page parse took 2.48 s on a busy CI runner, failing `< 2.0` checks that exist to catch quadratic blowup. `tests/timing.py` now times CPU at N and 4N, paired and alternated, and takes the median; 4x the input must cost under 8x (quadratic is about 16x). A test proves a quadratic function fails the check, so the check itself is tested.
- **A property counterexample can be the strategy's bug.** The click property's generator glued `…(model$))(model$…` with no space. The spec reads two `$` in one unspaced run as LaTeX math, which hides the parentheses. The fix was in `_join`, with the corrected case pinned as an `@example`. Product code, `QUERY_VERSION` and canonical forms were untouched.
- **Mutation shards grew past their limits without any hang.** 997 mutants each ran all 13 case tables, though one failing table already kills a mutant. `mutate.py` now runs the tables naming the mutant's file first and stops at the first failure, which cut one local slice from 755 s to 277 s with the same verdicts. It also stops a table past 10x its baseline (at least 60 s) and counts that mutant as killed (`TIMEOUT`), so no shard can be held by a hang.
- **A long property needs more shards, not more minutes.** The group-count property (TASK-176) takes 38–68 min per differential shard, and one slow runner pushed shard 7 past 110 min. The differential now runs as 12 shards, and the count comes from `strategy.job-total`, so it can't drift from the matrix.

## Dead ends — don't repeat these
- Raising a wall-clock constant. That hides a regression as easily as it hides a slow runner.
- Treating each red nightly as a flake to re-run. All three failure classes were real.

## Decisions (and what would change them)
- Growth ratio under 8x for 4x input. A legitimately N log N path that needs more headroom would change it, and that change would be stated per test.
