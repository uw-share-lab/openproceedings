# A nightly job that hits its time limit reports nothing, and a corpus can lack the edge a strategy needs

**Key lesson:** Check a scheduled workflow's job history (`gh run view <id> --json jobs`) before extending it: the nightly property jobs had been cancelled at their limits every night, which shows as "cancelled" with no test named, so give long pytest steps `-v` and a `timeout --signal=INT` a few minutes inside the job limit.

- **Date:** 2026-10-02 · **Task:** task-057 · **Area:** ops
- **Artifacts:** `.github/workflows/nightly.yml`, `backend/tests/differential/test_differential.py`,
  `backend/tests/fixtures/corpus/synthetic_5k.py` (`cap_records`, `cap_vocab`), `backend/tests/strategies.py`
  (`Vocab.cap`), `backend/tests/bench/report_80k.py` (its "Over budget" section)

## What we set out to do
Add differential@50k, the full benchmarks and parity to the nightly workflow, and stems near the 200-expansion
cap to the wildcard strategies.

## What we learned
- The nightly `properties` and `properties-oracle` jobs ran serially and were cancelled at 120 and 150 minutes
  on every run from 2026-09-28 to 2026-10-01 (`gh run view 36876401748 --json jobs`); only `suite-ci` and
  `mutate` ever reported a result. A timeout is a cancellation: the log ends mid-run with no test named. They
  now run under pytest-xdist.
- Under pytest-xdist, `-v` prints each test's node id when it starts and `[gwN] PASSED …` when it ends, and a
  SIGINT through `uv run` reaches pytest (exit 2; `timeout` itself exits 124). So `timeout --signal=INT` plus
  `-v` makes an overrun a failed step whose log shows the test that started with no result (checked locally
  with a sleeping test).
- One Hypothesis property can't be split by pytest-xdist. The differential's 50,000 examples run as 8 matrix
  jobs of 6,250, each with its own `--hypothesis-seed` (`OP_DIFFERENTIAL_SHARDS`), at about 0.15 CPU-seconds
  an example locally (200 examples: 37.5 s of user CPU, about 7 s of it imports and building the two engines;
  load average 80-190).
- The 5k corpus has no wildcard stem between 117 and 278 terms (2-letter roots give ~280-290 or ~900, 3-letter
  stems at most 117), so "stems near the cap" could not be drawn from it. Regenerating the corpus would move
  `CORPUS_HASH` and every contract, e2e and bench fixture built from it; 20 added records (`qca*` 199, `qcb*`
  200, `qcc*` 201 terms) give exact edges for the differential suite alone.

## Dead ends — don't repeat these
- Timing a 2,000-example differential run locally while other agents ran suites (load 65-190): wall time
  meant nothing; user CPU from `/usr/bin/time -p` on a 200-example run was the usable number.

## Decisions (and what would change them)
- Shards over one long job: one job at 50,000 would take ~4-5 h on a runner, close to the 6 h cap. Fewer
  shards if the proof run shows each finishing in a few minutes.
- The differential leaves `suite-ci`: its own job runs 25 times as many examples, and the test sets
  `deadline=None`, so the `ci` profile's deadline added nothing.

## Follow-ups
- [ ] none new: `mutate`'s nightly failures (a surviving mutant, "herestring treated as heredoc") are a gate
  finding outside this task, reported to the team lead.

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/skills/property-testing/SKILL.md`,
  `.claude/skills/testing-standards/SKILL.md`, `.claude/agents/differential-tester.md`, spec 07 §A/§E, spec 08 CI table
- Test or hook added? — `test_the_cap_stems_sit_at_the_cap` pins the cap edges in both engines
