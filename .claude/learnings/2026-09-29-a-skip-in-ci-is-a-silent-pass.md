# The additive OpenAPI check skipped on every PR, so a breaking API change would have passed CI

**Key lesson:** A test that skips when its input is missing is a silent pass in CI. When a check guards something CI must enforce, give CI a switch that turns the skip into a failure, and read the skip list in a PR run's log once, not just the pass count.

- **Date:** 2026-09-29 · **Task:** task-129 · **Area:** ci
- **Artifacts:** `.github/workflows/test.yml`, `backend/tests/contract/test_openapi_additive.py`, `.claude/skills/api-contract/SKILL.md`

## What we set out to do
Explain a third skipped test that showed up while measuring TASK-127's CI time ("5255 passed, 3 skipped").

## What we learned
- `test_openapi_additive` reads the released contract with `git show origin/dev:…`. actions/checkout fetches one commit, so `origin/dev` never exists in CI and the test skipped on every PR run (PRs 23, 24 and 26 all show it).
- The right baseline is the commit the change builds on (the PR's base SHA, or the pushed branch's previous tip), fetched by SHA. Comparing against the base branch's tip races with merges and can flag a missing additive field as a removal.
- `main` held only the specs before its first promotion, so "the base has no snapshot" must skip, but only when the base has no backend at all; otherwise a moved snapshot would hide a break.

## Dead ends — don't repeat these
- Fetching `refs/heads/<base_ref>`: promotion PRs into main then always failed (no snapshot on main) and the tip-vs-merge-commit race stayed.

## Decisions (and what would change them)
- `OPENAPI_BASELINE_REQUIRED=1` only in `test.yml`; locally and in nightly the test still skips without a baseline.

## Follow-ups
- [ ] none

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/skills/api-contract/SKILL.md`
- Test or hook added? — the required-baseline switch in `test_openapi_additive.py`
