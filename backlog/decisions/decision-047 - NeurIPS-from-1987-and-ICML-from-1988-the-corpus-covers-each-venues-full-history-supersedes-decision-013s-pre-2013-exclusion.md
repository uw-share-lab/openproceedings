---
id: decision-047
title: >-
  NeurIPS from 1987 and ICML from 1988: the corpus covers each venue's full
  history (supersedes decision-013's pre-2013 exclusion)
date: '2026-10-07 03:15'
status: accepted
---
## Context

decision-013 (2026-09-27) crawled every venue from 2013, ICLR's first year, and kept "years before 2013 out;
revisit only with a spec change and a reason from a review that needs them". Its reasons were comparability (a
quarter-century of NeurIPS alone, with no ICLR and a different ICML source, makes cross-venue counts
incomparable) and scope.

On 2026-10-06 the owner asked for the full history of NeurIPS and ICML to be indexed. ICLR is unchanged: it began
in 2013. Facts checked live that day (`docs/research/2026-10-06-pre-2013-neurips-icml-sources.md`):

- `proceedings.neurips.cc` serves every year from 1987, and the 1987–2012 pages have the 2013 shape.
- PMLR has no ICML volume before v28 (2013). The earlier proceedings are scattered: icml.cc keeps copies of the
  2007–2012 sites; 2004–2008 are in the ACM DL, whose terms forbid scraping; earlier years were Morgan Kaufmann print.
- dblp lists every ICML paper, but dblp.org forbids crawling (robots.txt `Disallow: /`, an Anubis challenge on its
  pages and API). Its sanctioned bulk route is the monthly snapshot XML release on Dagstuhl DROPS: CC0, a DOI per
  release.
- dblp has no abstracts. Official ICML pages with per-paper abstracts survive, live or as Internet Archive captures,
  for 2001, 2003, 2004 and 2007–2012 (`docs/research/2026-10-06-icml-pre-2013-abstract-sources.md`).

## Decision

The owner decided (2026-10-06): the corpus covers NeurIPS from 1987 and ICML from 1988, superseding decision-013's
"years before 2013 stay out".

- **NeurIPS 1987–2012** come from the proceedings site, as 2013–2020 do (TASK-204).
- **ICML 1988–2012** come from one pinned dblp snapshot release, `10.4230/dblp.xml.2026-10-03` (sha256
  `20e45961…aebe969`), read through the shared HTTP layer from drops.dagstuhl.de and never from dblp.org: each
  year's main-conference proceedings key is data (`ingest/dblp_icml.toml`), every record is `main`/`accepted`
  but the 27 entries the table lists as no paper (2009's workshop and tutorial summaries and invited talks, 1994–
  1996's invited-talk abstracts: track `other`, found by the review gate), and every claim names the release
  (TASK-205). 1989, 1991 and 1992, held as the International Workshop on Machine
  Learning, are the series' meetings those years and count as the main conference.
- **Abstracts for ICML 1988–2012** come only from official ICML/IMLS pages, live or a pinned Internet Archive
  capture, named in `ingest/icml_sites.toml`, and attach to a dblp record only by an exact title key that one page
  entry and one paper of the year share; anything else stays `null` and is counted (TASK-206, owner update of
  2026-10-06). This is a clause of spec 01's abstract-source rule ("OpenReview's, else the proceedings page's"):
  the official ICML pages, for dblp's records only.
- **ICML 1997 and 1998** (owner decision of 2026-10-07, TASK-207): their official pages hold submission-time
  abstracts beside the authors' postal addresses, e-mail addresses and phone and fax numbers, and are used for the
  abstract text alone. The parsers keep the text after an `Abstract` heading up to the form's next field; one that
  still holds an e-mail address, a phone-shaped number, a contact label or a postal code is withheld whole and
  counted (`site_withheld`), and none of those details reaches a record, the snapshot, the index, an export or a log
  line (tested). The abstract claim's evidence says it is a submission-time abstract from the official page, with
  the Internet Archive capture's timestamp.
- **Old abstract text** is cleaned the way decision-044 cleans control characters: a NeurIPS page's placeholder
  (`Abstract Unavailable`) is no abstract, and PDF-extraction codes are repaired (`(cid:173)`, a soft hyphen at a
  line end, is removed so the word is whole; any other `(cid:N)` becomes a space), each counted and noted in the
  claim's evidence. A focused review found both in the 1987–2012 pages (nearly all before 2004); no page from
  2013 on holds either.

## Consequences

- Spec 00 open question 3, spec 01 (§Sources: the NeurIPS row's years, new dblp and ICML sites rows; the crawl
  window; `op ingest dblp`), spec 02, 04 and 07, the coverage page, README and CLAUDE.md say so (TASK-203).
- Per-venue year coverage differs before 2013: NeurIPS and ICML have cells, ICLR none. The coverage page states
  each venue's span and that a search without `year:` compares venues over different years (copy deck CV-7).
- Record schema 5: the `dblp` and `icml_site` sources and the `dblp-<key>` native id. A `dblp-` id is valid only for
  ICML 1988–2012, so dblp and PMLR (2013 on) never hold one venue-year. dblp's keys are unique, so a takedown
  follows a dblp record across a corrected year, as it does a PMLR one.
- Most pre-2013 ICML records are title-only: 1,290 of 2,675 have an abstract (none in 1988–2000, 2002, 2005, 2006).
  The coverage page's "No abstract" column and its all-missing flag show it per venue-year.
- NeurIPS 1987–2012 main gets official counts from each year page's own count; ICML 1988–2012 has no official
  accepted count (dblp is a bibliography, not the conference's statement), so those cells are reported, not gated.
- Moving to a newer dblp release is a change to `dblp_icml.toml` and a snapshot-diff event; a year marked under
  another release is refused on replay.
- 1997 and 1998 have official pages with submission abstracts and authors' contact details. They were first left
  out as an owner question; on 2026-10-07 the owner decided to use their abstract text only (the Decision's 1997/1998
  bullet, TASK-207). A submission abstract can differ from the published paper's, and the claim's evidence says
  which it is. The published titles can differ from the submitted ones too, so some of those years' abstracts find no
  exact title key and stay unattached (counted as `site_unmatched`), as in every other year.
- 1989, 1991 and 1992 are exported under the ICML name (`International Conference on Machine Learning (ICML
  <year>)`), like every ICML year, though they were held as the International Workshop on Machine Learning: a
  normalisation spec 04 §Exports and the coverage report's scope lines state.
- The crawl window a search record or methods text cites is when sources were read. For ICML 1988–2012 that is
  when the pinned release was read; the records reflect the release (its DOI and date) and the official pages'
  captures, not a crawl on those dates. The coverage report the methods text cites says so in its scope lines
  (spec 05 §Methods text), rather than a new clause in the methods text itself.

## Owner confirmation (2026-10-07)

After PR #120 the owner confirmed three labelling choices this record and `dblp_icml.toml` already make, so they
are settled, not open: (a) ICML 1989, 1991 and 1992, which dblp files as workshops (the International Workshop on
Machine Learning), are indexed as ICML main-conference years; (b) ICML 2010's invited application papers stay in
the main track; (c) the 27 entries that are no paper (2009's workshop and tutorial summaries and invited talks,
1994–1996's invited-talk abstracts) stay track `other`. No code or data changed with this confirmation.
