# A property that failed `too_slow` only under load was paying for Hypothesis's cold Unicode cache

**Key lesson:** Before you tune or suppress a Hypothesis health check, measure the window it times: wrap `ConjectureRunner.record_for_health_check` in a scratch pytest plugin and log the draw time and the overruns of the first 10 valid examples. Here that showed one cold-cache draw (~0.85 s, in a fresh worktree) against a 2.5 s local limit, with every other window far below its limit. Wall-clock checks belong only in the profiles CI runs.

- **Date:** 2026-10-01 · **Task:** task-146 · **Area:** tooling
- **Artifacts:** `backend/tests/conftest.py`, `backend/tests/unit/test_hypothesis_profiles.py`, `.claude/scripts/tests/test-hypothesis-profiles.sh`, decision-024, `.claude/skills/property-testing/SKILL.md`

## What we set out to do
Stop property tests from failing on a loaded machine (`too_slow`, deadlines) without hiding real slowness (TASK-146).

## What we learned
- `too_slow` times only the draws of the first 10 valid examples, and fails above the larger of 1 s and 5 deadlines: 2.5 s under the old `dev` (500 ms), 10 s under `pr` and `ci`, and 30 s with `deadline=None`. `data_too_large` fails at 20 overruns before 10 valid examples, which doesn't depend on load (Hypothesis 6.168, `internal/conjecture/engine.py`, `record_for_health_check`).
- `test_a_split_always_has_the_id_count` had a 0.87 s window with `.hypothesis/` removed and 0.002 to 0.012 s with it present. The cost is `.hypothesis/unicode_data/<ver>/codec-v2-utf-8.json.gz` (plus `charmap.json.gz`), built on the first `st.text()` draw. Every new agent worktree starts without it.
- Reproduced with 32 × `yes > /dev/null` on 8 CPUs (load 76 to 123), `rm -rf .hypothesis` before each run: the old `dev` profile failed `too_slow` 5 times in 5 ("only generated 2 valid inputs after 4.65 seconds"). The new `dev` passed 5 times in 5.
- At `pr`, every property's window was at most 0.75 s. Over 300 seeds, `engine_asts(vocab())` and the facets test's `filtered_asts()` took at most 0.84 s and overran at most once. So the per-test `too_slow`/`data_too_large` suppressions were cargo: removed, with the targeted files passing at `pr` (148 passed).
- A `function_scoped_fixture` suppression on a test whose fixture is module-scoped does nothing (`test_search_overlap.py`).
- The CI runners showed none of this: of the 146 `test` runs since 2026-09-26, none failed.

## Dead ends — don't repeat these
- A probe run with a list of files held in a zsh variable ran no tests ("no tests ran"): zsh doesn't word-split `$FILES`. Use `${=FILES}` or an array.
- The probe recorded nothing at `max_examples=10`: the window closes at the 10th valid example, and the zero example uses one of the 10. Use 15 or more.

## Decisions (and what would change them)
- decision-024: `dev` has no deadline and suppresses `too_slow`. `pr`, `ci` and `nightly` keep every check. Revisit if PR runners start failing timing checks without a code cause.

## Follow-ups
- [ ] none

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/skills/property-testing/SKILL.md` (§Health checks and deadlines, with the load recipe), `.claude/skills/testing-standards/SKILL.md` (rule 5)
- Test or hook added? — `backend/tests/unit/test_hypothesis_profiles.py`, case table `.claude/scripts/tests/test-hypothesis-profiles.sh`, and 12 `profiles:` mutants in `.claude/scripts/mutants/gates.json`

## Addendum — 2026-10-01: the profiles inherited Hypothesis's built-in `ci` profile on CI runners
**Key lesson:** Register every Hypothesis profile with an explicit parent (`settings.get_profile("default")`), and test the profiles with `CI=true` as well, because GitHub Actions sets `CI` and Hypothesis then loads its built-in `ci` profile at import, which a parentless `register_profile` copies.
- The PR's first CI run failed: `get_profile("pr").suppress_health_check` was `[too_slow]` on the runner and `[]` locally. Reproduced with `CI=true uv run pytest backend/tests/unit/test_hypothesis_profiles.py`.
- Built-in `ci` (Hypothesis 6.168): `derandomize=True`, `database=None`, `deadline=None`, `too_slow` suppressed. So since the profiles were written, CI's `pr`, `ci` and `nightly` were derandomized, ran the same examples every run, and couldn't fail `too_slow`.
- Dead end: tracing conftest double imports, xdist workers and `testpaths` collection. All were fine; the difference was one environment variable.
- `make tooling` hid the failure: the case table sent pytest's output to `/dev/null`, so CI printed nothing but `Error 1`. It now prints pytest's report on failure.
- Propagated: conftest `BASE`, the case table's `CI=true` run, 4 more `profiles:` mutants (16 in all), `pr` derandomized on purpose (the PR gate stays deterministic; `ci` and `nightly` explore), the property-testing skill and decision-024.

## Addendum — 2026-10-05
- **A nightly on the exact release candidate found two failing properties the scheduled nightly could not.** The scheduled run tested a sha before the batch; one dispatched on the candidate (run 37353576315) failed `properties (ingest)` at the nightly profile. `test_caps` stripped `…` then spaces once, so `… …x` left `…x`, which the record rightly refuses: a test bug. `test_dedup_props`' abstract-merge property asserted that a crawled cluster's status is always listable, which the product never promised: decision-037 refuses only a record that is *no listing*, and a listing can be one by a RIS row's or a note's own proceedings URL (TASK-174's shape), so a rejected note can be one. The first fix, an `assume` that proceedings sources claim only listable statuses, covered the one blob, discarded about 29% of examples, and still failed on two pools reviewers built; the property now asserts the product's rule (`listable or is_listing`) with both pools as `@example`s, and TASK-198 asks whether a RIS-only listing should keep the exemption. Evidence: the printed blobs replay as `DidNotReproduce`; the reviewers' pools. Lesson: run the nightly on the exact candidate before a tag; and when a property fails, assert the rule the product implements rather than `assume` away the input, since the first counterexample is rarely the only one.
