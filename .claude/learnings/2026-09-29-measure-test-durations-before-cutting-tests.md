# CI's backend step took 25 minutes because of 25 property tests, not because there were too many tests

**Key lesson:** When a test suite feels slow, run `pytest --durations` at the profile CI uses before deleting or merging tests. Here 25 Hypothesis properties at 2,000 examples took 87% of the time, and the other 5,199 tests took 218 s combined. Cutting tests would have saved almost nothing; cutting examples per PR and parallelising did.

- **Date:** 2026-09-29 · **Task:** task-127 · **Area:** ci
- **Artifacts:** `.github/workflows/test.yml`, `.github/workflows/nightly.yml`, `backend/tests/conftest.py` (the `pr` profile), `Makefile`

## What we set out to do
Cut the ~25-minute backend step of the required `test` check. The first idea was that the suite simply had too many tests.

## What we learned
- `pytest --durations=40 --hypothesis-profile=ci`: 5,224 tests in 1,650 s; the slowest 25, all Hypothesis properties, took 1,432 s. The slowest single tests were a clause-edit property (331 s) and the Tantivy-vs-oracle differential (308 s).
- 200 examples per PR under pytest-xdist ran in ~3 min locally against ~9.5 min serial; nightly's new `suite-ci` job keeps every property at 2,000.
- The `dev` profile also carries a 500 ms deadline, which a loaded shared runner could trip under xdist: PR CI uses a `pr` profile (200 examples, the 2 s ci deadline). A profile is example count *and* deadline; changing which one CI uses changes both.

## Dead ends — don't repeat these
- A `timeout 900 uv run pytest …` profiling run hung past its limit: `timeout` signalled `uv`, not the Python child. Call `.venv/bin/pytest` directly when a run needs a time limit.

## Decisions (and what would change them)
- Owner's choice (2026-09-29): 200 examples + xdist on PRs, 2,000 nightly. A property failure that needs more than 200 examples now surfaces within a day rather than on the PR. Revisit if nightly `suite-ci` starts catching failures PRs let through.

## Follow-ups
- [ ] none

## Propagated to
- Skill / agent / CLAUDE.md updated? — property-testing, testing-standards, pr-workflow and query-grammar skills; ci-engineer and differential-tester agents; `/exactness-check`; specs 07 and 08; CLAUDE.md; README
- Test or hook added? — the nightly `suite-ci` job
