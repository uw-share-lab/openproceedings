# Hypothesis's "invalid" overruns come from its mutator copying spans across one shared label

**Key lesson:** To cut a recursive strategy's overruns, draw every decision that changes how much is drawn after it (leaf or group, part count, list length, padding on or off) from its own `st.sampled_from`, not `st.booleans`/`st.integers`/`st.lists`. Hypothesis's mutator copies a span over another span with the same label, and a copy that needs more choices than the case had overruns.

- **Date:** 2026-10-01 · **Task:** task-153 · **Area:** query
- **Artifacts:** `backend/tests/strategies.py` (`click_cases`, `wrap_cases`, `ParseCase`, `_GROUP_SIZES`, `_QUERY_NODES`, `_VALUE_LISTS`), `backend/tests/unit/test_clauses.py` (the one-wrap and single-value-click properties), `.claude/skills/property-testing/SKILL.md`

## What we set out to do
Replace `assume()` on a successful parse in the one-wrap and single-value-click properties with strategies that build
parseable queries, as TASK-145 did for the year edit, without testing less.

## What we learned
- On dev at the `pr` profile, the one-wrap property threw away 27-30% of draws through `assume()` (41/101, 55/115,
  44/104 invalid). The click property's invalid share was 59-65% (293/493, 365/565, 316/516), of which `assume()`
  rejected 30-32% of all draws and overruns made up the rest. Evidence: `--hypothesis-show-statistics`, 3 runs each.
  After the change neither property rejects anything. At `pr` (now derandomized) one-wrap is 8/68 invalid and click
  18/218; over earlier random runs, one-wrap was 6-16% and click 5-12%, all overruns.
- Nearly all overruns are `ConjectureRunner.generate_mutations_from`, not generation. Evidence: a scratch harness that
  wraps `test_function` counted 201 overruns from mutation against 8 from generation, over 4×200 click cases. The
  mutator copies one span over another of the same label, then reruns with exactly the old number of choices
  (`max_choices = count`). A copy that turns a leaf into a group, or lengthens a list, runs out of choices. All
  `st.integers`/`st.booleans` draws share one class label, and every `st.lists` element shares `ONE_FROM_MANY_LABEL`.
  The `ONE_FROM_MANY` group alone caused 114 of about 180 mutation overruns in click before the fix. Giving each such
  decision its own `sampled_from` (a distinct element tuple gives a distinct label) took click's overruns from about
  26% to about 10% of cases with a trivial test body, and `queries()` from about 13% to 6%.
- A strategy that cuts padding back to the parse limit finds edges that `assume()` hid. `wrap_cases` landed on short
  repeated words at 1,800-1,870 code points (`trust` × 300). There the combined wrap of every field is too long but
  each field's own wrap fits, so `filter_clauses` parses 5 times while every field is toggleable. The property's cost
  bound read "every field toggleable" as "written in one wrap" and failed. The code matches spec 02 ("at most
  five"). Evidence: the dev version of the property fails on that input as an `@example` (`assert 5 <= (0 + 1)`).
- The near misses still see what the property must catch. In 5 temporary mutants of `clauses.py` and `parser.py`, the
  generated cases alone, without the pinned examples, killed every one: the all-negative check removed, the splice's
  widest edit never checked, the wraps never checked or a too-long combined wrap taken for every field, and a nested
  field reported toggleable.

## Dead ends — don't repeat these
- A trivial test body (`def t(x): pass`) gives different absolute invalid counts than the real property, in either
  direction. Use it to compare strategy variants, then confirm on the real test.
- Without derandomization, invalid shares vary by about ±5 points between runs, so take several runs before
  concluding anything (`pr` is derandomized since decision-024, so one `pr` run is one number).

## Decisions (and what would change them)
- The valid-only strategies keep more complex queries than the old survivors of `assume()`, so a smaller share of
  venue/track/status clauses is toggleable per case (about 50-60% against 60-83%). Non-toggleable verdicts rose from
  about 25% to about 45%, and those are where a wrong "toggleable" is caught. If a toggleable-edit bug slips past,
  weight `_CLICK_BODIES` toward "one atom".
- `clause_queries` was removed when its last user went. `year_edit_cases` was not given own-label decisions (its
  invalid share stays at TASK-145's 10-20%); doing so would change TASK-145's strategy for no failing check.

## Follow-ups
none

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/skills/property-testing/SKILL.md` (as built: `click_cases`, `wrap_cases`;
  gotcha: overruns are mutator copies across a shared label)
- Test or hook added? — the pinned `@example`s in `backend/tests/unit/test_clauses.py` (one per near-miss code, the cap
  boundaries, and `trust` × 300)
