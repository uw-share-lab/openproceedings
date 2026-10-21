# Check the mutate shards' headroom before the release candidate's nightly

**Key lesson:** Before the nightly that has to be green for a release, read the previous nightly's mutate shard times; if any shard is within about 15 minutes of its 140-minute cap, add shards first, since a candidate that adds mutants (as gate work does) will push it over.

- **Date:** 2026-10-19 · **Task:** TASK-265 (v0.4.0 release) · **Area:** ci
- **Artifacts:** `.github/workflows/nightly.yml` (mutate matrix, 12 → 16), nightly runs 39191247944 and the one before it

## What we set out to do
Get a green nightly on the 0.4.0 candidate (993772e9), as §Release step 1 asks, then promote.

## What we learned
- **The cap was hit by growth, not a flake.** Shard times rose night by night: 39–68 min on 2026-10-14,
  up to 135 min (shard 12) on 2026-10-18, and on the candidate shard 10 was cut off at 140 after ~135 mutants
  with none surviving, and shard 3 took 138. The candidate's own TASK-253/254 cmdparse mutants were the last step.
- **A cut-off shard fails the nightly, correctly.** Its unchecked mutants would otherwise go unchecked, so the
  release waits on a new matrix and a second ~2.5 h nightly, not on a re-run of the one job (the shard's
  mutant set is fixed, so it would land at the cap again).
- **The trend was visible a day early.** `gh run view <run> --json jobs` gives each shard's start and end; one
  look at the 2026-10-18 nightly (135 min) would have prompted the matrix change before the candidate was cut.
- **A fix merged after the release bookkeeping makes `CHANGELOG.md` stale.** #171 landed after #170, so
  `changelog.py --check --release 0.4.0` failed on `dev`, and would have failed step 6 on `main`. Run
  `make changelog` again on a `release/*` branch (the generator leaves those out of the list, so that PR doesn't
  make it stale in turn), and dispatch the nightly only once that has merged too.

## Dead ends — don't repeat these
- Re-running only the timed-out shard: the same mutants on the same runner size end at the same cap.
- Chaining release steps as `git push … | tail -n 2 && gh pr create …` in one background script: the pipe's
  status is `tail`'s, so a push the pre-push hook refused (a fresh worktree with no `node_modules`) went on to
  the PR steps and an hour of polling for a PR that didn't exist. Keep the push's own status, and `make sync`
  in every new worktree before its first push.
