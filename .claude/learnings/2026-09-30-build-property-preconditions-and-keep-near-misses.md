# A property built to meet its preconditions stops seeing the verdicts it used to filter on

**Key lesson:** When you replace `assume()` with a strategy that builds only inputs meeting the precondition, also build near misses (one step past each rule) and assert the code refuses them for the right reason; otherwise a property that used to catch a wrongly-accepted input (a false "toggleable") can no longer see one.

- **Date:** 2026-09-30 · **Task:** task-145 · **Area:** query
- **Artifacts:** `backend/tests/strategies.py` (`year_edit_cases`), `backend/tests/unit/test_clauses.py` (`test_every_year_edit_on_a_toggleable_clause_parses_and_edits_only_that_clause`), `.claude/skills/property-testing/SKILL.md`

## What we set out to do
Stop the year-edit property failing `filter_too_much` (every time at seed 197275319351247031457750150800712837025)
by generating queries with a toggleable year clause instead of drawing any clause or near-cap query and
`assume()`ing it.

## What we learned
- The old property threw away about 70% of its draws (4 pr runs: 526/726, 695/895, 395/595, 595/795 invalid;
  41% failed to parse, 20% had a year clause that wasn't toggleable), and of the 200 it kept, almost none were
  near-cap (a near-cap query nearly always had a canonical form over the cap, or a year filter nested under
  its ORs) and only 2 to 7% had a year clause to splice (evidence: `--hypothesis-show-statistics` with
  `event` counts on a scratch copy of the old test).
- Building only valid inputs cut the rejections to zero, but the first version let two mutants of
  `query/clauses.py` survive that nothing in the new property could see: `too_long` never reported for edits
  up to 2,100 code points, and a negated year clause reported toggleable. The old property caught the first
  (it drew over-cap queries and asked `filter_clauses`); neither caught the second. Adding near misses (about
  one case in five, plus one `@example` per reason) kills both (evidence: mutation runs on a scratch copy).
- `--hypothesis-show-statistics` counts Hypothesis's own overruns as invalid too: "exceeded maximum test case
  size" in observability output (`HYPOTHESIS_EXPERIMENTAL_OBSERVABILITY=1`), with no "gave up" line. They come
  all through a run, not just early (a per-case timeline of one run showed them spread evenly), so they are not
  only the early size cap in `internal/conjecture/engine.py`; tree mutations that copy one span over another
  are the likely rest. `clause_queries()` alone showed 118 invalid per 200, `near_cap_queries(1_800, 2_000)` 36.
  The rebuilt property shows 27 to 58 per 200 (20 pr runs: 19 under 20%, one at 22.5%), none rejected by the
  test. Fewer drawn near-cap parts (two instead of six) and span labels per recursion depth changed nothing.
- `filter_clauses` costs several parses (150 to 250 ms on a 2,000-character OR), one parse about 5 to 40 ms:
  sizing a padded query by bisection with `filter_clauses` made the test take minutes.

- A fit criterion that checks only the edit can pass a query that doesn't parse: the ci profile (2,000
  examples) found `(` × 63 around `NOT NOT year:2021`, too deep itself while the widest edit spliced over it
  is two levels shallower. The property's assert caught it (no silent skip); the fit now parses both.

## Dead ends — don't repeat these
- Checking the fit at each doubling of the near-cap parts, to stop drawing early: more invalid cases, not fewer.
- `filter_clauses(...).year.toggleable` as the fit test inside the strategy: correct but several times slower
  than parsing the query and its widest year edit, which is what it checks for the year clause.

## Decisions (and what would change them)
- The strategy sizes padding by parsing the query and its widest year edit, and the test asserts the real
  `filter_clauses` verdict on every case → the grammar can drift from the parser's rules without the fit
  noticing, but the assert fails loudly. A rule change in `clauses.py` would mean updating `year_edit_cases`.
- Near-cap cases draw at most six parts and pad with distinct filler rather than drawing ~2,000 characters of
  parts → fewer draws and a fit that ends in filler; the drawn parts still cover the near-cap shapes, the filler
  covers the length.

## Follow-ups
- [ ] none: other properties in `test_clauses.py` still `assume()` a parse (lines 237, 289); they don't fail the
  health check today, so they are left as they are (named in the PR as a deferral).

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/skills/property-testing/SKILL.md` (as built: `year_edit_cases`;
  gotcha: invalid counts include Hypothesis's overruns)
- Test or hook added? — `test_the_year_edit_property_passes_at_the_seed_that_failed_its_health_check` and the
  pinned near-miss examples in `backend/tests/unit/test_clauses.py`
