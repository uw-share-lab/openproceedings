# The crawl cache is the evidence for a string table, and scrub.py read `BT@ICLR2024` as an email

**Key lesson:** Build an exact-string table from the real crawl cache (every distinct value, with counts) and give each row a recorded note trimmed from that cache. Then table-test each retained label, because `scrub.py` can quietly rewrite a controlled string: it turned `BT@ICLR2024` into `synthetic.person16@example.org`.

- **Date:** 2026-09-30 · **Task:** task-101 · **Area:** ingest
- **Artifacts:** `backend/src/openproceedings/ingest/classify.py` (`V2_PRESENTATION`), `backend/tests/fixtures/http/openreview/v2/*/notes-presentation-*.json`, `backend/tests/fixtures/http/scrub.py` (`PERSON`), spec 01 §Presentation

## What we set out to do
Parse `presentation` from API v2 `content.venue` using a per-venue-year table of exact, verified strings.

## What we learned
- The v2 cache's public projection keeps every world-readable content key, `content.venue` included. So one
  offline pass over `data/cache/openreview/v2/http` lists every distinct string per venue-year × track ×
  status, with counts, and needs no live request. The research doc's vocabulary missed `BT@ICLR2024`, the
  D&B and position-track wordings, and `NeurIPS 2025 Position Paper Track`, which states no presentation.
- Those cache pages are recorded, public exchanges. Trimming a page to one note per string and running it
  through `scrub.py` makes a fixture under the existing conventions (`_recorded.run` names the cache,
  `trimmed` gives the original row count).
- `scrub.py`'s email pattern `[^\s@]+@[^\s@]+` matched `BT@ICLR2024` and replaced the label. Only the table
  test caught it: the row's note was no longer found. An email needs a dotted domain, so the pattern now
  requires one (a regression test is in `test_fixture_scrub.py`, and `V2_VENUE_LABELS` has a row for it).
- Workshop venue strings are free-form (about 335 of them mention oral, spotlight or poster, one wording per
  workshop), so a table can't cover them. Scoping the lookup to accepted, non-workshop notes keeps the
  unmapped count meaningful, and it was 0 on the real cache.

## Dead ends — don't repeat these
- Mapping a string from its wording alone. `ICML 2023 OralPoster` and `ICML 2025 spotlightposter` needed
  the counts to justify them (155 + 1,673 = the 1,828 accepted ICML 2023 notes). `ICML 2026 regular` stays
  unmapped because nothing says what it means.

## Decisions (and what would change them)
- The table is keyed by venue-year, and each string carries the track its venueid must give, so a D&B
  string on a main-track note is unmapped. A venue that reuses one string across tracks would change this.
- `none` rows (Tiny Papers tiers, blogposts, competition, NeurIPS 2025 position without Oral) are known
  strings that state no presentation, so they aren't counted as unmapped.

## Follow-ups
- [ ] none. ICLR/ICML 2026 strings get rows when those years are crawled; `presentation_unmapped` flags them.

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/skills/record-schema/SKILL.md`, `.claude/skills/openreview-api/SKILL.md` (presentation bullet, fixture recipe), `.claude/skills/logging-standards/SKILL.md`
- Test or hook added? — `test_the_table_holds_exactly_the_fixture_backed_strings` (every row fixture-backed), `test_a_venue_label_with_an_at_sign_but_no_domain_stays_real_and_an_email_does_not`
