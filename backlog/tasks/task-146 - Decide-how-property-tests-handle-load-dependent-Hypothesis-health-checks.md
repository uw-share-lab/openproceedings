---
id: TASK-146
title: Decide how property tests handle load-dependent Hypothesis health checks
status: To Do
assignee:
  - '@jeevanp03'
created_date: '2026-09-30 06:40'
labels:
  - tests
  - ci
dependencies: []
references:
  - backend/tests/conftest.py
  - .claude/skills/property-testing/SKILL.md
  - .claude/skills/testing-standards/SKILL.md
ordinal: 123000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Property tests fail on a loaded machine for reasons that are not bugs. Known cases: `backend/tests/unit/ingest/test_openreview_v1_authors.py::test_a_split_always_has_the_id_count` failed the `too_slow` health check at a load average of about 90 during parallel `make test` runs (it passed on rerun and with its seed); TASK-140's verification saw `test_a_facet_of_a_field_the_query_never_filters_counts_its_matches` miss the dev profile's 500 ms deadline at load ~90 (passed on 3 seeded reruns); and there was one unidentified intermittent failure on the TASK-137 branch. Several agents run `make test` (pytest -n auto, dev profile) in parallel worktrees, so load like this is normal locally. Today the property-testing skill allows `suppress_health_check=[HealthCheck.too_slow]` only for the differential suite, yet `test_facets_equal.py` and `test_highlight_speed.py` also suppress it, and each profile in `backend/tests/conftest.py` sets only max_examples and deadline. The risk on the other side: hiding a strategy or code path that really became slow.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A written decision (property-testing skill, and a decision record if it changes a profile) on how the dev, pr, ci and nightly profiles treat `too_slow` and deadlines, e.g. suppress load-dependent checks in dev/pr while nightly keeps them, or make the slow strategies cheaper, with the reason
- [ ] #2 Real slowness still fails somewhere: at least one profile run in CI (nightly or pr) keeps the too_slow check or an equivalent timing gate, shown by a test or mutant that makes a strategy slow and is caught
- [ ] #3 test_a_split_always_has_the_id_count passes under the chosen local profile at high load (e.g. `make test` alongside a CPU-saturating job), or its strategy is made cheaper
- [ ] #4 The existing per-test suppressions (test_facets_equal.py, test_highlight_speed.py, the differential suite) either match the new rule or are removed, and the skill and the conftest docstring describe the rule as built
<!-- AC:END -->
