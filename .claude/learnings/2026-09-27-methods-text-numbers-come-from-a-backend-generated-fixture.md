# The methods text can't hold a hand-typed number if its tests read the API's own answers and the spec's own sentence

**Key lesson:** To prove a generated citation has no hand-typed numbers, test it against a fixture the backend generates from real API calls (normalised ids and clock, kept current by a contract test) and assert every number in its prose appears in the record the API sent; pin "verbatim" by reading the example straight out of the spec file, not by copying it into the test.

- **Date:** 2026-09-27 · **Task:** task-044 · **Area:** frontend
- **Artifacts:** `frontend/src/lib/methods-text.ts` and `.test.ts`, `backend/tests/contract/record_fixture.py`, `backend/tests/contract/test_frontend_record_fixture.py`, `frontend/src/components/record/record-fixture.json`, `frontend/src/lib/export.ts`, `frontend/src/components/{export,record}/`

## What we set out to do
Build the Export menu, Save search record, `/record/[id]` and the PRISMA methods text (spec 05 §Components 7–8),
with every number from the API and none typed by hand.

## What we learned
- **A backend-generated fixture of real answers carries the numbers.** `record_fixture.py` saves five records
  (a limit, an empty identification string, an all-negative one, one default, a Scholar record) and four
  searches on a slice of the synthetic corpus, plus `/parse` of each record's `canonical` and
  `identification_query`; a record id is random and `searched_at` is the clock, so both are replaced with fixed
  values before writing. The frontend tests interpolate the fixture's fields into their expected strings, and
  one property asserts every digit run in the methods prose is a number in the record JSON.
- **"Verbatim" is enforceable.** The spec 05 example is read from `docs/specs/05-frontend.md` with a regex,
  whitespace collapsed, placeholders substituted, and compared exactly with the generator's output for a record
  with the example's values (evidence: `methods-text.test.ts`, "writes the spec's example sentence for
  sentence").
- **The default and limit clauses need no new API field while the query version matches.** `/parse` of the
  record's `canonical` reports `defaults` and each field's span in that string (TASK-091), so slicing gives
  `track:(datasets_benchmarks OR main OR position)` and a user's `year:2020..2026` exactly; when `/parse` runs
  under another `query_version` the text says less rather than guess.
- **The fixture corpus is RIS-only, so every real record is non-citable.** Tests that need methods text flip
  `identification_citable` (and the crawl kind) on a copy; every count stays the API's.
- **`openapi-fetch`'s `parseAs: "stream"` gives the headers before the body**, so an export can be abandoned
  (`response.body.cancel()`) when `X-Index-Version` or `X-Total` differs from what was shown.
- **A CDP `Runtime.evaluate` of a DOM node returns no value** (`returnByValue` can't serialise it), so a smoke
  script's "wait for element" must return a boolean or it times out on an element that is there.

## Dead ends — don't repeat these
- Copying `data/indexes` into the shared session scratchpad's `data/` (other agents use it): make a private
  subdirectory (`scratchpad/t044/data`) for `op serve`, since the record store is written beside the index.
- Expecting a second Chrome download of the same `Content-Disposition` name to appear as a new file: it
  replaced the first; clear the download directory before each export you check.

## Decisions (and what would change them)
- The record page requests the replay automatically after the stored read (no button), because the spec's e2e
  expects `reproduced` on arrival; revisit if replay cost under load matters more (TASK-047/065).
- The methods text and exports wait for the replay to settle, so a `mismatch` never flashes citable content;
  a 429/`API_BUSY` replay shows them with "Replay: waiting".
- The export formats stay disabled until `/parse` has reported on the shown query, so the status warning can't
  be skipped by a fast click.

## Follow-ups
- [ ] The TASK-044 strings have no separate copy task; include them in TASK-047's first usability round.
- [x] Do not add a second citable E2E fixture now: unit and contract fixtures already cover citable methods
  text, while changing the synthetic snapshot's provenance would expand TASK-046 without a new user-facing
  behavior. Reopen this only if a production-source full-stack fixture is introduced.

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/skills/nextjs-conventions/SKILL.md`, `.claude/skills/search-records/SKILL.md`, `CLAUDE.md`, spec 05, the export/records design doc
- Test or hook added? — `backend/tests/contract/test_frontend_record_fixture.py`, `frontend/src/lib/{methods-text,export,replay-status}.test.ts`, `frontend/src/components/{export,record}/*.test.tsx`
