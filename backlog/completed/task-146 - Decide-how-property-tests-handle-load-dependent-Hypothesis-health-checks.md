---
id: TASK-146
title: Decide how property tests handle load-dependent Hypothesis health checks
status: Done
assignee:
  - '@jeevanp03'
created_date: '2026-09-30 06:40'
updated_date: '2026-10-01 04:54'
labels:
  - tests
  - ci
dependencies: []
references:
  - backend/tests/conftest.py
  - .claude/skills/property-testing/SKILL.md
  - .claude/skills/testing-standards/SKILL.md
  - .github/workflows/nightly.yml
ordinal: 123000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Property tests fail on a loaded machine for reasons that are not bugs. Known cases: `backend/tests/unit/ingest/test_openreview_v1_authors.py::test_a_split_always_has_the_id_count` failed the `too_slow` health check at a load average of about 90 during parallel `make test` runs (it passed on rerun and with its seed); TASK-140's verification saw `test_a_facet_of_a_field_the_query_never_filters_counts_its_matches` miss the dev profile's 500 ms deadline at load ~90 (passed on 3 seeded reruns); and there was one unidentified intermittent failure on the TASK-137 branch. Several agents run `make test` (pytest -n auto, dev profile) in parallel worktrees, so load like this is normal locally. Today the property-testing skill allows `suppress_health_check=[HealthCheck.too_slow]` only for the differential suite, yet `test_facets_equal.py` and `test_highlight_speed.py` also suppress `too_slow` (and `test_differential.py` and `test_facets_equal.py` suppress `data_too_large`), while no profile in `backend/tests/conftest.py` sets `suppress_health_check`. The risk on the other side is hiding a strategy or code path that really became slow. Read the testing-standards and property-testing skills and the conftest profiles first; the nightly workflow (`.github/workflows/nightly.yml`, TASK-127) runs the whole suite at `ci` and properties at `nightly`; the differential suite runs only at `ci` until TASK-057.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A written decision (property-testing skill, and a decision record if it changes a profile) on how the dev, pr, ci and nightly profiles treat `too_slow`, `data_too_large` and deadlines, e.g. suppress load-dependent checks in dev/pr while nightly keeps them, or make the slow strategies cheaper, with the reason
- [x] #2 Real slowness still fails somewhere: at least one profile run in CI (nightly or pr) keeps the too_slow check or an equivalent timing gate, shown by a test or mutant that makes a strategy slow and is caught
- [x] #3 test_a_split_always_has_the_id_count passes under the chosen local profile at high load, reproduced by a named recipe (e.g. `yes > /dev/null` once per CPU, or `stress-ng --cpu <ncpu>`, while `uv run pytest -n auto` runs) with the load average recorded, or its strategy is made cheaper
- [x] #4 The existing per-test suppressions (`too_slow` in test_facets_equal.py, test_highlight_speed.py and the differential suite; `data_too_large` in test_facets_equal.py and test_differential.py) either match the new rule or are removed, and the skill and the conftest docstring describe the rule as built
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Root cause of the authors too_slow: a cold .hypothesis/unicode_data cache (fresh worktree) makes the first st.text() draw cost ~0.85 s of the 10-example window, against the old dev limit of 2.5 s (max(1 s, 5 x 500 ms)). Probe: a scratch pytest plugin wrapping ConjectureRunner.record_for_health_check. At pr every property's window was <= 0.75 s; engine_asts(vocab()) and filtered_asts() over 300 seeds <= 0.84 s and <= 1 overrun (limit 20), so the per-test too_slow/data_too_large suppressions were removed.
AC3 recipe: 32 x 'yes > /dev/null &' on 8 CPUs, ~45 s wait, rm -rf .hypothesis before each run; load 76-123 (uptime). Old dev (deadline 500, no suppression) failed too_slow 5/5; new dev passed 5/5.
AC2: test_hypothesis_profiles.py (sleeping strategy fails pr, passes dev) + 8 'profiles:' mutants, all killed (mutate.py --match profiles: --jobs 4). The pr mutant is also killed by the slow-strategy test alone.
Targeted: HYPOTHESIS_PROFILE=pr pytest -n 4 on differential, facets, highlight-speed, search-overlap, profiles, v1 authors, v1 collapse props: 148 passed.

Review round 1 (qa-auditor Must): pr/ci/nightly deadlines now pinned exactly, 2 more mutants (10 profiles: mutants, all killed with --jobs 4); scan test forbids per-test suppress_health_check. Full make test at cc603bf (before review fixes): backend 5968 passed, 2 skipped; frontend 3052 passed. make lint and make tooling pass.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Decision-024: Hypothesis wall-clock checks are gates only on CI runners. The local dev profile has no deadline and suppresses only too_slow (local make test shares 8 CPUs with other worktrees; load 90 to 340); pr, ci and nightly keep their deadlines (2 s, 2 s, none) and every health check, so a slow strategy still fails the PR's test job. Root cause of the authors-property failures: a cold .hypothesis/unicode_data cache costs the first st.text() draw ~0.85 s of the 2.5 s old dev limit. Reproduced at load 76-123 (32 x yes on 8 CPUs, cold cache): old dev failed too_slow 5/5, new dev passed 5/5. Removed the per-test too_slow/data_too_large suppressions (measured windows <= 0.84 s, <= 1 overrun over 300 seeds) and a no-op function_scoped_fixture one. Pinned by test_hypothesis_profiles.py (sleeping strategy fails pr, passes dev; exact deadlines; no per-test suppression) and 10 profiles: mutants via case table test-hypothesis-profiles.sh. Skills property-testing and testing-standards updated. Verified: make test (5968 backend passed, 2 skipped; 3052 frontend), make lint, make tooling, mutate.py --match profiles:.
<!-- SECTION:FINAL_SUMMARY:END -->
