# Refusing a `)` glued to a field prefix would have broken facet clicks on the real review strings

**Key lesson:** Before refusing a query form, run `test_clauses.py`: a facet click splices `field:(…)` over a clause span that can follow a `)` directly (the Trust-Evals strings end `…)(source:ICLR OR …)`), so a rule that refuses what the splice writes makes real clauses uneditable.

- **Date:** 2026-10-02 · **Task:** TASK-158, TASK-160 · **Area:** query
- **Artifacts:** `backend/src/openproceedings/query/lexer.py` (`after_pass`, `filter_value_next`),
  `backend/src/openproceedings/query/parser.py` (`reported(glue=False)`), `backend/tests/unit/test_parser.py`
  (`GLUED_CLAUSES`), decision-027, `backend/tests/contract/test_frontend_clip_golden.py`,
  `frontend/src/lib/clip-golden.json`, `frontend/src/test/hostile.ts`.

## What we set out to do
Make spec 02's glued-parenthesis rule and the lexer agree for filter values (TASK-158), and clip the API
values the remaining `Coded` messages quote (TASK-160).

## What we learned
- The symmetric rule (refuse a filter clause glued to a parenthesis on either side) failed four
  `test_clauses.py` cases: two Trust-Evals strings, `year:(2019)status:accepted`, and a year-edit property seed.
  The splice writes `…)venue:(ICLR)`, which that rule refused (evidence: the first run of
  `pytest backend/tests/unit/test_clauses.py` on this branch). Only the `(` side was a real inconsistency.
- A glued-parenthesis error covering a filter value silenced the value's own check: the parser's
  `reported()` treats any covered span as "already said". `year:..2022(x)` reported only the glue. The glue
  error now covers a separate array that a value's check ignores.
- QUERY_VERSION need not move when only typed input becomes refused: replay re-parses the stored canonical
  string, and the canonical form never writes a value before `(` (clauses are joined by ` AND `).
- Vite's JSON loader rejects a lone-surrogate escape (`"\ud800"`), which Python's `json` writes happily; a
  golden that must carry one stores code points.

## Dead ends — don't repeat these
- Writing a Python escape such as backslash-u-202e through the Write tool put the literal character (a
  right-to-left override) in the source, and the same slip reached this entry's first draft; re-escape
  non-ASCII with a script and check with `grep -P '[^\x00-\x7f]'` (or a Cc/Cf scan) before committing.
- The first field-value message fired after any field, so `title:model(s)` lost its plural hint (review
  round 1): a "field's value" test must use the filter-field set, not `Kind.FIELD`.

## Decisions (and what would change them)
- Decision-027: refuse a value glued to a following `(`, keep `)field:` and `)(` accepted, QUERY_VERSION stays
  2. A reducer that wrote a space before every splice would let `)field:` be refused too.
- TASK-160: clip each value of a clause, not the whole clause, so the 47-code-point default track clause
  reads as before.

## Follow-ups
- None: these tasks leave nothing open.

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/skills/query-grammar/SKILL.md`, `.claude/skills/error-diagnostics/SKILL.md`, spec 02, spec 05
- Test or hook added? — `test_parser.py::test_a_parenthesis_glued_to_a_filter_clause`, `test_frontend_clip_golden.py`, the hostile-value tests in `exclusions.test.ts` and `replay-status.test.ts`
