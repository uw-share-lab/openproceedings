---
id: decision-024
title: >-
  Hypothesis wall-clock checks are gates only on CI runners: the local dev
  profile has no deadline and suppresses too_slow (TASK-146)
date: '2026-10-01 04:36'
status: accepted
---
## Context

Agents run `make test` (pytest-xdist, the `dev` profile) in several worktrees at once on one 8-CPU machine.
The 1-minute load average reached 90, and on 2026-09-30 about 340. Property tests then failed for reasons that
were not bugs. `test_openreview_v1_authors.py::test_a_split_always_has_the_id_count` failed the `too_slow`
health check twice, on different branches, and passed on rerun. A facets property missed the `dev` profile's
500 ms deadline (TASK-140's verification).

Hypothesis's `too_slow` check times the draws of the first 10 valid examples. It fails above the larger of
1 s and 5 deadlines: 2.5 s under `dev`'s 500 ms, 10 s under `pr` and `ci` (2 s), and 30 s with no deadline
(`nightly`). In a fresh worktree `.hypothesis/unicode_data` is empty, and the first `st.text()` draw builds it,
which costs ~0.85 s of draw time. A threefold slowdown put the authors property past 2.5 s. On 2026-10-01, with
32 `yes` processes running (load 76 to 123), the old `dev` profile failed that property `too_slow` 5 times in 5
cold runs, and the profile chosen here passed 5 times in 5. A deadline measures wall time the same way.

`data_too_large`, `filter_too_much` and `large_base_example` don't depend on load: for a given seed they come
out the same at any speed. At the `pr` profile every property's health-check window took at most 0.75 s.
Over 300 seeds each, the 5k-corpus strategies (`engine_asts(vocab())` and the facets test's `filtered_asts()`)
took at most 0.84 s and overran at most once (the limit is 20). So the per-test `too_slow` and `data_too_large`
suppressions in the differential, facets and highlight-speed tests were hiding nothing they needed to.

Of the 146 `test` workflow runs since 2026-09-26, 144 passed and 2 were cancelled; none failed, and no nightly
failure since TASK-127 was a health check or a deadline. The runners aren't shared with other worktrees' runs,
so their clocks measure the code.

Options considered:
1. Suppress `too_slow` and drop the deadline in both `dev` and `pr`, and keep them only in `nightly`. Rejected:
   a slow strategy would then surface a day late, in a workflow that has been red for other reasons, instead
   of on the PR that caused it. The PR runners don't show the load problem.
2. Keep every check and make the slow strategies cheaper, e.g. warm Hypothesis's Unicode cache at session
   start. Rejected as the whole answer: it removes the cold-cache case but not the load. At 42 times
   oversubscription even a 0.07 s window exceeds 2.5 s, and deadlines would still fail.
3. Scale `dev`'s deadline with the load average. Rejected: the profile would depend on when the run started,
   and the rule would be harder to state.
4. **Chosen:** turn wall-clock checks off only in `dev`, and keep them in every profile CI runs.

## Decision

The local `dev` profile has no deadline and suppresses only `HealthCheck.too_slow`. `pr`, `ci` and `nightly`
keep their deadlines (2 s, 2 s, none) and suppress no health check. Every other health check is on in every
profile, and no test suppresses a health check on its own (a test fails on one). A per-test `deadline=None`
with a comment is still allowed for an example that is long by design.

## Consequences

- A local `make test` can no longer fail on timing. Real slowness is still caught on every PR, by the `pr`
  profile in the required `test` job, and nightly by `ci` and `nightly`.
  `backend/tests/unit/test_hypothesis_profiles.py` pins this: a sleeping strategy fails `pr` and passes `dev`.
  The `profiles:` mutants in `.claude/scripts/mutants/gates.json` (case table
  `.claude/scripts/tests/test-hypothesis-profiles.sh`) cover each profile's settings.
- To check timing before pushing, run `HYPOTHESIS_PROFILE=pr uv run pytest <file>` on a quiet machine.
- `dev` used to be stricter than `pr` (500 ms against 2 s). Code with examples between 0.5 and 2 s was failing
  locally on code the PR gate accepts. Now a local pass predicts the PR result, except for timing.
- Changed: `backend/tests/conftest.py` (the profile and its docstring), the property-testing and
  testing-standards skills, and the per-test settings in `test_differential.py`, `test_facets_equal.py`,
  `test_highlight_speed.py` and `test_search_overlap.py`. The last one's `function_scoped_fixture` suppression
  did nothing, since its fixture is module-scoped. Every remaining per-test `deadline=None` got a reason
  comment, and five cheap properties (at most ~55 ms an example) went back to the profile deadline.
- No effect on matching, `index_version` or search records.
- Revisit if the PR runners start failing `too_slow` or deadlines without a code cause (then consider option 1
  for `pr`), or if local timing failures come back under another name.
