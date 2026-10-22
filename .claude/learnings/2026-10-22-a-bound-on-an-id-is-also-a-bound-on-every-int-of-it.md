# A length bound on an id's form must also bound every parser that reads the same digits

**Key lesson:** When an id form gets a length bound, find every place that reads those characters before the model sees them (URL parsers, a crawler's `int()`, an importer's volume) and bound each one the same way, before `int()`: the model's regex refuses the record, but a parser that ran first can still crash on Python's 4,300-digit limit or a non-ASCII digit.

- **Date:** 2026-10-22 · **Task:** task-280, task-281 · **Area:** ingest
- **Artifacts:** `backend/src/openproceedings/ingest/record.py` (`MAX_NATIVE_KEY`, `MAX_NATIVE_DIGITS`), `backend/src/openproceedings/ingest/urls.py` (`_NUMBER`), `backend/src/openproceedings/ingest/ris.py` (`_int`), `backend/src/openproceedings/ingest/sources/ojs.py` (`_number`), `backend/src/openproceedings/ingest/acm_table.py` (`DOI_DIGITS`), `backend/src/openproceedings/ingest/caps.py` (`LIST_CAPS`, `listed_total`), `backend/src/openproceedings/export.py`, `docs/results/2026-10-22-list-counts-and-native-ids.md`, decision-054, decision-055

## What we set out to do
TASK-280: cap how many authors (500) and keywords (200) a record keeps, trimmed and flagged, and say so in every
export. TASK-281: bound every native-id form (a key of at most 200 characters, a number of at most 12 digits), a
record past a bound refused, record schema 9 → 10.

## What we learned
- **The model's regex is the last reader of an id, not the first.** A PMLR volume is read by `urls.pmlr` (from a URL),
  by `ris._int` (from an RIS volume claim) and by `int()` in the record check; an OJS article id by `sources/ojs.py`'s
  header parse and `urls.ojs_article`; an ACM DOI number by `acm_table.paper_doi`. Each ran `int()` on unbounded
  digits before any record existed, so 5,000 digits raised a bare `ValueError` that aborted the crawl. Each now reads
  at most 12 digits (after leading zeros, for URLs), and the OJS harvest raises a `CrawlError` (`oai_unreadable`)
  before `int()`. Evidence: `test_urls.py::test_a_pmlr_volume_past_the_bound_names_no_paper`,
  `ojs/test_ojs_parse.py::test_an_article_id_past_the_bound_is_a_crawl_error_never_a_bare_value_error`,
  `test_record.py::test_a_native_id_past_the_int_digit_limit_is_refused_without_reading_it`.
- **`str.isdigit()` is not "ASCII digits".** `'²'.isdigit()` is true and `int('²')` raises. `ris._int` now checks
  `isascii()` too.
- **A bound can make another rule's branch unreachable, so remove it.** decision-053 kept a URL "already the page of
  the record's own id" whole when it was over the cap. With the id bounded, that page is at most about 250
  characters, so no URL over 2,048 can be it. The branch went rather than stay untested (decision-055).
- **A constant shared across an import cycle needs a test that pins it.** `record` imports `acm_table`, so
  `acm_table.DOI_DIGITS` can't import `record.MAX_NATIVE_DIGITS`. It is defined twice and
  `test_record.py::test_the_acm_tables_doi_bound_is_the_native_ids` asserts they are equal.
- **"Et al." has a native form in BibTeX but not in RIS.** BibTeX's `and others` is the standard. RIS has no such tag,
  and an `AU  - et al.` line is imported by Covidence as an author, so a cut list is one `N1` note instead.
- **A count read back from evidence must only trust its own writer's form.** `caps.listed_total` answers only for a
  list exactly at the cap whose note says it kept exactly the cap. Evidence that merely contains the note's words says
  nothing of a shorter list (`test_caps.py`, the look-alike rows).
- **Measure first, and the version question answers itself.** The read-only pass over 2026-10-16-03eab0ef56c4 (about
  110 s) found at most 95 authors, 54 keywords and a 53-character id, every record valid at schema 10, and
  `cap_record` changing none. So `snapshot_hash` and `index_version` are unchanged; only the manifest's
  `record_schema_version` (and `FILES_HASH`) move.

## Dead ends — don't repeat these
- Bounding only `record.PROCEEDINGS_NATIVE`. The record refused the id, but the crawlers never got that far.

## Decisions (and what would change them)
- A refused record (decision-055), not a trimmed id: cutting an id renames the paper. Revisit if a real key passes
  100 characters or a real number 10 digits.
- A cut list is trimmed, not refused (decision-054), as decision-026 and decision-053 trim text. Revisit if a real
  record comes within 2× of a cap.

## Follow-ups
- None found.

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/skills/record-schema/SKILL.md` (§Native ids bounds, §Versions, §The
  ingest caps), `.claude/skills/bibtex-format/SKILL.md`, `.claude/skills/ris-format/SKILL.md`,
  `.claude/skills/api-contract/SKILL.md`, `.claude/skills/snapshots/SKILL.md`, `.claude/skills/dedup-rules/SKILL.md`,
  `.claude/skills/logging-standards/SKILL.md`, `CLAUDE.md` (the `caps.py` entry), `docs/specs/01-ingestion.md`,
  `docs/specs/04-backend-api.md`.
- Test or hook added? — tests at the bound and one past it per form and per crawler (`test_record.py`, `test_pmlr.py`,
  `test_dblp.py`, `test_dblp_aaai.py`, `test_ris.py`, `ojs/test_ojs_parse.py`, `crossref/test_crossref_mine.py`,
  `test_urls.py`), at count−1/count/count+1 (`test_caps.py`), and per export format (`contract/test_lists_cut.py`).
