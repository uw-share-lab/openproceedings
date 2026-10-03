# A hand-typed partial /coverage stub crashed the builder tests once the home line read one more field

**Key lesson:** In frontend tests, stub a GET with the backend-generated fixture (`coverage-fixture.json`, `record-fixture.json`), never a hand-typed partial body: a partial body passes `tsc` (JSON isn't checked against the schema) and breaks whichever unrelated test first renders a component that reads a field it left out.

- **Date:** 2026-09-29 · **Task:** task-110 · **Area:** frontend
- **Artifacts:** `frontend/src/components/coverage/coverage-line.tsx`, `frontend/src/builder/concept-builder.test.tsx`, `frontend/src/components/search/search-workspace.test.tsx`

## What we set out to do
Make the home page's coverage line read `GET /coverage` in the `/coverage` page's words (index, records, venues, window).

## What we learned
- Two test files stubbed `/api/v1/coverage` as `{ totals: {...} }` only. The old line read `totals.records`, so they passed. The new line reads `snapshot.crawl_dates`, and `concept-builder.test.tsx` failed with `Cannot read properties of undefined (reading 'crawl_dates')` and three unrelated-looking assertion failures (the empty state renders inside `SearchWorkspace`). Evidence: `npm test --workspace frontend` before the stub fix, 3 failed in `src/builder/concept-builder.test.tsx`.
- Switching both stubs to `coverage-fixture.json` fixed it and pins the line to the same answer the backend's `test_frontend_coverage_fixture.py` keeps current.

## Dead ends — don't repeat these
- Tempting but rejected: guarding the component against missing fields (`snapshot?.crawl_dates`). The schema says the fields are required, so a guard only hides a bad stub. Recognise it by a crash in a test file you didn't touch.

## Decisions (and what would change them)
- The home line drops `GET /meta`: every fact comes from one `GET /coverage` answer, so it can't mix two index versions mid-swap. Reverse if the line ever needs a fact only `/meta` serves.

## Follow-ups
- none

## Propagated to
- Skill: `.claude/skills/testing-standards/SKILL.md` §Fixtures ("Frontend stubs answer with the API's own fixtures").
- Test or hook added? — no: the two offending stubs are fixed; a lint for inline API bodies would be noisy for deliberate error bodies.
