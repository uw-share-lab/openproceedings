# A decision table built from one recorded forum missed ICLR 2020's spotlights and talks

**Key lesson:** Build a status table from the tally of a whole venue-year's live strings, not from the forums that happen to be recorded as fixtures. Watch a crawl report's `unmapped` count: a nonzero value on an exact-match table is a missing string, not noise.

- **Date:** 2026-09-29 · **Task:** task-123 · **Area:** ingest
- **Artifacts:** `backend/src/openproceedings/ingest/sources/openreview_v1.py` (the ICLR 2020 table), `backend/tests/fixtures/http/openreview/v1/iclr-2020/forum-accepted-{spotlight,talk}.json`, `backend/tests/unit/ingest/test_openreview_v1.py::test_iclr_2020_spotlight_and_talk_decisions_are_accepted`

## What we set out to do
Explain ICLR 2020 main's miss in the first full coverage trial: 531 indexed accepted against the official 687 (−22.7%).

## What we learned
- The v1 crawl report said `unmapped: {"decision_note": 156}`, and the venue-year held 156 records with status `unknown`. 531 + 156 = 687, the official count (evidence: the trial snapshot `f2ba9c975ae4`'s manifest).
- The cached decision notes hold `Accept (Poster)` 531, `Accept (Spotlight)` 108, `Accept (Talk)` 48 and `Reject` 1,526, and 108 + 48 = 156. The table mapped only `Accept (Poster)` and `Reject`, because the one recorded ICLR 2020 accepted forum was a poster (evidence: the tally in `docs/research/2026-09-27-openreview-and-proceedings-facts.md`).
- Exact-match tables are right for status (never guess an unseen string), but "seen" has to mean the whole crawl. The fixture run recorded one forum per decision kind it knew about.

## Dead ends — don't repeat these
- None.

## Decisions (and what would change them)
- `Accept (Talk)` → presentation `oral` (the presentation vocabulary is oral/spotlight/poster, and ICLR 2020's talks were its orals).

## Follow-ups
- [ ] task-054 — the other trial misses (ICLR 2013/2014 archive, NeurIPS OpenReview-accepted absent from proceedings)

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/skills/openreview-api/SKILL.md` (the 2020 forms, and "seen" means the whole crawl's tally)
- Test or hook added? — the recorded spotlight and talk fixtures and their test
