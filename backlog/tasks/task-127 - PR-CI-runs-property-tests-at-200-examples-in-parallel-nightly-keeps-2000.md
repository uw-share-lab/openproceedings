---
id: TASK-127
title: 'PR CI runs property tests at 200 examples in parallel; nightly keeps 2,000'
status: In Progress
assignee:
  - '@jeevanp03'
created_date: '2026-09-29 22:32'
updated_date: '2026-09-29 23:04'
labels:
  - ci
  - tests
dependencies: []
ordinal: 111000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
PR CI's backend step takes ~25 min. Measured 2026-09-29 (--durations, ci profile): 25 Hypothesis property tests take 1,432 of 1,650 s (87%); the other 5,199 tests take 218 s. The owner chose: PR CI at the dev profile (200 examples) with pytest-xdist across the runner's CPUs; nightly runs the whole backend suite at the ci profile (2,000) in addition to its existing 50k jobs, so no property loses depth, only detection moves to within a day.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 PR CI's backend step runs the suite with pytest-xdist at the dev Hypothesis profile and finishes in well under 10 minutes on the shared runner (measured on the PR's own run)
- [x] #2 The nightly workflow runs the whole backend suite at the ci profile (2,000 examples), besides its existing 50k and exhaustive jobs
- [ ] #3 The suite passes under xdist locally and in CI (no test depends on order or shared state); make test uses xdist too
- [x] #4 pr-workflow, ci docs, CLAUDE.md and the README describe the new split; step names and the test.yml timeout/comment are accurate
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
- pytest-xdist (>=3.8, locked 3.8.0 + execnet 2.1.2) added to the root dev dependency group with `uv add --dev`; `uv sync --locked` still works.
- test.yml: backend step is `uv run --locked pytest -q -n auto --hypothesis-profile=dev` (default `--dist load`); renamed; timeout 60 -> 30 with an accurate comment.
- nightly.yml: new `suite-ci` job (60 min) runs the whole backend suite at `--hypothesis-profile=ci` with `-n auto`; the three existing jobs are unchanged.
- Makefile `make test` runs the backend with `-n auto` (profile still from HYPOTHESIS_PROFILE, default dev).
- xdist safety: every index-building fixture is module/session-scoped over tmp_path_factory (per worker), no test writes to a shared repo path (regenerators run only under `__main__`), no fixed ports (tests bind port 0), env changes go through monkeypatch. No isolation fixes were needed. Fixture setup is under 8 s each, so the per-worker rebuild is cheap and `--dist load` beats `loadscope`.
- Local timings (8 CPUs, machine heavily loaded by other jobs, load avg 30-200): serial dev 9m26s; xdist dev 2m54s and 3m13s (5256 passed, 2 skipped both times); xdist ci 11m24s, bounded by the differential property (8 min at 2k). Slowest at dev under xdist: facets_equal 93 s, differential 79 s.
- Docs: property-testing, testing-standards, pr-workflow skills; ci-engineer and differential-tester agents; spec 07 and 08; CLAUDE.md; README; conftest and test_differential docstrings.
- AC#1 (CI time) and the CI half of AC#3 can only be verified on the PR's own run.
- Noted, not changed: `test_export_braced.py` pins `@settings(max_examples=3_000)` and `max_examples=2_000` on two properties, so they run that many under every profile; they cost little.

Review round 1 (6fe6166): PR CI uses a `pr` profile (200 examples, 2 s deadline) rather than `dev` (500 ms), so a slow example on a shared runner under xdist can't fail the required check.
<!-- SECTION:NOTES:END -->
