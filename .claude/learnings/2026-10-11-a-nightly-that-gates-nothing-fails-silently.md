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

## Addendum — 2026-10-11 (TASK-239)
- **The growth check charged the garbage collector to the large side.** `test_a_hostile_page_is_parsed_in_linear_time[icml2007_paper]`
  failed the queue build for PR #138 (38176036366, ratio 8.09) and PR #140's `test` (38197206724, 8.24). The small
  page kept its local 70 ms in every pair but the first, whose small call took 0.33-0.47 s; the large page took
  0.5-0.76 s against 0.26 s locally. A discrete 0.3-0.4 s event is a full collection: it walks the xdist worker's
  whole heap, and it fires once enough objects have survived since the last one, which the 407 KB page's
  ~41,000-element tree does about once a call and the 107 KB page seldom. Logging `gc.get_stats()` around
  `growth` in a local `make test`-style run (`-n 4`) reproduced it: ratio 5.45, large 366 ms, eight full
  collections inside the measurement; with the collector paused, 3.84 and 246 ms. `tests/timing.py`'s `cpu` now
  pauses the cyclic collector while it times a call; allocation, copying and reference-counted freeing stay
  timed. Freeing a call's cyclic garbage (every parsed HTML tree, through its parent links) moves after the call:
  linear, and qa-auditor measured it at 12 ms against a 227 ms parse.
- **The suspected cache effect didn't hold up.** Seven memory-bandwidth burners beside the measurement left the
  ratio at 3.5-4.0 with the collector paused, and a cache miss rate doesn't make a single small call 6x slower in
  one pair only.
- **The pause keeps the check's power.** `test_timing.py` shows a quadratic in allocation (tuple copying, ratio
  ~16-20) fails as well as the quadratic in work, and that no collection starts inside a timed call. Local
  negative controls: the former `_find` scans in place of `_Closers` fail the LaTeX check at 15.9, and a
  page-rescanning step added to the ICML parse fails the icml2007_paper check at 10.5-13.4.
- **Three linear-time checks had their own timers.** `test_latex_scan.py` and `ingest/test_html.py`
  (`escape_bare_lt`) batched by hand, and `test_highlight_speed.py` compared unpaired minima, the method
  TASK-171's recovery showed flakes. All three now use `growth(..., calls=N)`. The differently shaped CPU bounds
  (the capped-abstract ceiling in `ingest/test_caps.py`, `test_many_searches_cost_no_more_than_one`, the
  long-field NEAR ceiling in `engine/test_highlight.py`) time with `cpu`, so no CPU-time measurement in the test
  suite but `timing.py`'s remains, the `backend/tests/bench/` scripts aside. The wall-clock timers left are
  concurrency waits and HTTP latency bounds, plus one growth check across threads:
  `contract/test_verification_scale.py`'s `width_is_free` times requests that `TestClient` serves on another
  thread, where this thread's CPU clock sees nothing, so it stays on the wall clock with its 2x + 500 ms margin.
- **A test of "no collection inside the call" must count only inside the call.** The first version recorded every
  collection while its callback was installed; the test's own allocations after `cpu` returned could start a
  youngest-generation collection (code-reviewer reproduced it at 4 of 12 starting counts). A flag set only during
  the timed body fixed it.
- Propagated to: `backend/tests/timing.py` (docstring), `.claude/skills/testing-standards/SKILL.md` §CPU growth checks.
- Dead end: raising the bound for the largest input. It hides what the collector costs, and that cost scales with
  whatever else the worker holds, so no constant bound is safe.
