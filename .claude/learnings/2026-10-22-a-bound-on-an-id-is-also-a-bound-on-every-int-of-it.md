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
- TASK-282: `http._seconds` and the dblp year readers still trust `str.isdigit()` (see the closing addendum).
- TASK-275 (note added): a NeurIPS listing warning logs its see-also links uncapped through `scrub()`.

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/skills/record-schema/SKILL.md` (§Native ids bounds, §Versions, §The
  ingest caps), `.claude/skills/bibtex-format/SKILL.md`, `.claude/skills/ris-format/SKILL.md`,
  `.claude/skills/api-contract/SKILL.md`, `.claude/skills/snapshots/SKILL.md`, `.claude/skills/dedup-rules/SKILL.md`,
  `.claude/skills/logging-standards/SKILL.md`, `CLAUDE.md` (the `caps.py` entry), `docs/specs/01-ingestion.md`,
  `docs/specs/04-backend-api.md`.
- Test or hook added? — tests at the bound and one past it per form and per crawler (`test_record.py`, `test_pmlr.py`,
  `test_dblp.py`, `test_dblp_aaai.py`, `test_ris.py`, `ojs/test_ojs_parse.py`, `crossref/test_crossref_mine.py`,
  `test_urls.py`), at count−1/count/count+1 (`test_caps.py`), and per export format (`contract/test_lists_cut.py`).

## Addendum — 2026-10-22 (review round 1)
- **Stripping zeros for the length check isn't enough if `int` still gets the zeros.** `ris._int` counted digits after
  `lstrip("0")` but called `int(value)` on the whole string, so 5,000 zeros then `202` still raised past the 4,300-digit
  limit (code, security and QA review each reproduced it). It now converts the stripped digits. Lesson: check and
  convert the same string. Evidence: `test_ris.py`, the "a zero-padded PMLR volume" row.
- **The sweep for unbounded `int()` has to cover every crawler, not only the id forms.** Review found two more: a PMLR
  page's `Volume N:` heading (`pmlr._VOLUME_PREFIX`) and a NeurIPS year page's stated count (`neurips._COUNT`). Both are
  now bounded in the regex, so an oversized number is no match (`heading_mismatch`, or no stated count). And
  `urlparse` raises on an unclosed IPv6 host, which aborted an RIS import from claim evidence: `ris._readable` now
  skips such a URL. Evidence: `test_pmlr.py::test_a_volume_heading_reads_at_most_twelve_digits`,
  `test_neurips.py::test_a_stated_count_past_sixteen_characters_states_none`,
  `test_ris.py::test_a_proceedings_url_urlparse_refuses_is_skipped_never_an_aborted_file`.
- **Leading zeros must count the same way in every reader.** `ojs._number` counted them and `urls._NUMBER` didn't, so
  the harvest refused a padded article id that the URL parser read. All now count digits after leading zeros.
- **A guard on which claim a value is read from needs a case where the guard decides.** `RecordFile.lists_cut` reads
  only a claim holding the record's own list, and keeps the largest count. Neither choice was tested until a record
  with a cut *losing* claim (no `and others`) and two cut claims in both orders (700, not 600) were added
  (`contract/test_lists_cut.py`).
- **The manifest and the exports must use one rule.** `is_trimmed` matched the count note on a list of any length while
  `listed_total` required one exactly at the cap; `is_trimmed` now calls `listed_total`.

## Addendum — 2026-10-22 (review round 2)
- **Evidence text is input too, and it travels.** RIS evidence (`scholarmend:proceedings_page <url>`) is validated by
  no URL check, and it is read again long after import: by dedup's abstract attribution, which a snapshot load runs
  per record. A `http://[x` there aborted the whole build. `dedup._site` and `_names_native` now read such a URL as
  naming nothing, and `ris._readable` covers the `UR` lines too. Lesson: when fixing a parser crash at one call site,
  grep every caller of the same parser for untrusted input (here `urls.proceedings_site`/`names_native`; the Scholar
  comparison already had `_named`). Evidence: `test_dedup.py::test_an_evidence_url_urlparse_refuses_names_no_site_and_never_aborts_the_build`.
- **`or "0"` is a branch.** `value.lstrip("0")` of an all-zero string is empty, and `int("")` raises; the mutation run
  found no test for it until the "a PMLR volume of zeros" row.
- **A bound in a regex can change which match wins.** Bounding `Volume N:` let a first heading with a huge number be
  skipped for a later one; `heading()` now lets the first heading of that shape decide (`_VOLUME_HEADING`).

## Addendum — 2026-10-22 (review round 3)
- **"Grep every caller" means every caller of the primitive, not of our wrapper.** Round 2 fixed `urljoin` in the PMLR
  and NeurIPS listings, and round 3 found the same bare `urljoin` in the ICLR archive listing (`iclr._paper_anchor`)
  and the AAAI library's redirect check (`aaai_library.same_capture`). Both now go through `html.joined` or a
  `ValueError` guard. Evidence: `test_iclr.py::test_a_link_urljoin_refuses_names_no_paper_never_a_bare_value_error`,
  `aaai_library/test_aaai_library.py::test_a_redirect_location_urlparse_refuses_names_no_capture`.
- **A guard's return value needs a test, not just its existence.** The test that `_names_native` doesn't crash passed
  with it returning `True`, which would let an unreadable page merge two papers. A row in
  `test_an_abstract_that_is_not_the_imports_own_page_is_no_evidence` now pins `False`.
- **Dropping an unreadable link can change what the rest means.** A PMLR block that loses an unreadable OpenReview
  link would read as having no forum (or one forum, when it had two). The whole block is now unlinked instead; a
  NeurIPS see-also is kept as written so the crawl still reports it unfollowed.

## Addendum — 2026-10-22 (review round 4)
- **The half-read rule applies to every listing that tries several links.** The ICLR 2015-2016 list items try each
  anchor in turn, so an unreadable OpenReview link let the item be read from its arXiv link, without the forum.
  `iclr._paper_anchor` now names no paper when any of its links is unreadable, as `pmlr.parse_volume_index` does
  (`test_iclr.py::test_a_link_urljoin_refuses_names_no_paper_never_a_bare_value_error`).

## Addendum — 2026-10-22 (closing)
- **The `isdigit` fix was made where the bound was, not everywhere `isdigit` is.** `ris._int` gained `isascii()`, but
  three readers still trust `str.isdigit()`: `sources/http.py` `_seconds` (the `Retry-After` header of a 429 or 5xx,
  and `ratelimit-remaining`/`ratelimit-reset` on every 200 via `_respect_budget`; urllib decodes headers as latin-1,
  so one `0xB2` byte from any crawled host makes `float('²')` abort the run), and the dblp year readers in `sources/dblp.py` and `sources/dblp_aaai.py` (`int('²')`
  raises, `int('١٩٨٠')` reads 1980). Filed as TASK-282 rather than fixed in this backlog-only PR after review. The
  closing docs review found the network-facing one; the addendum's first draft named only dblp. Lesson: once a
  primitive is found unsafe, run `grep -rn isdigit backend/src` and check every hit, not only the files the task
  touched.
