# AAAI, AIES, FAccT and IASEAI: sources, census and section table (checked 2026-10-09 and 2026-10-10)

This note supports `backend/src/openproceedings/ingest/ojs_sections.toml` (decision-049) and the new-venues design
(`docs/plans/2026-10-09-new-venues-design.md`).

It records:
- the live facts gathered on 2026-10-09;
- the ojs.aaai.org census and its reconciliation;
- two server quirks the harvest had to handle;
- the section-to-track decisions, including the sections left for the owner to review;
- the dblp census behind `dblp_aaai.toml` (AAAI 1980–2008, 2026-10-10);
- the ACM census behind `acm_proceedings.toml` (FAccT 2019–2026, AIES 2018–2023), the PMLR v81 row and the
  facctconference.org pages (2026-10-10).

Every count below was read live on 2026-10-09 (UTC; the late fetches, the 39173 retry and the dblp check are
2026-10-10, and say so).

## ojs.aaai.org (AAAI 2010–2026, AIES 2024–2025, IASEAI 2026)

- **Access.** robots.txt disallows only `/cache/` and sets no crawl delay. The server takes 2–3 s a page, and the
  harvest paces at least 3 s between requests. OAI-PMH runs at `/index.php/{AAAI,AIES,IASEAI}/oai`.
  - `Identify` gives earliest datestamp 2020-06-02 and `deletedRecord` persistent.
  - Formats: `oai_dc`, `marcxml`, `jats`, `rfc1807`, `oai_marc`. Pages hold 100 records, and resumption tokens
    expire after 24 h.
- **Record shape.**
  - `dc:creator` is "Last, First".
  - `dc:description` is the abstract (about 960 characters on the 2010/2018/2019 samples).
  - `dc:source` names the volume and issue, e.g. "Proceedings of the AAAI Conference on Artificial
    Intelligence; Vol. 34 No. 01: AAAI-20 Technical Tracks 1; 540-547".
  - Each record has exactly one `setSpec`, which is its journal section.
  - Licence: `dc:rights` is "Copyright (c) <year> …". There is no open licence, so committed fixtures are
    scrubbed (decision-004).
- **Volumes.**
  - AAAI: year = volume + 1986 (Vol. 24 = 2010 … Vol. 40 = 2026).
  - AIES: year = volume + 2017.
  - IASEAI: year = volume + 2024.
  - An OJS issue is not a track. AAAI 2026 has 48 issues, mostly "Technical Tracks N", and one issue can mix
    IAAI, EAAI and student abstracts. So the track comes from the record's section.
- **Article ids** are unique across the three journals, so a record's native id is `ojs-<id>`.

### AAAI

- 172 issues, Vol. 24 (2010) – Vol. 40 (2026). Issues per volume: 2010–2014 3 each (No. 1 AAAI, No. 2 IAAI,
  No. 3 EAAI); 2015–2017 2; 2018 1; 2019 1 ("AAAI-19, IAAI-19, EAAI-20"); 2020 10; 2021 18; 2022 11; 2023 13;
  2024 21; 2025 28; 2026 48.
- Articles on the issue pages, IAAI and EAAI included:

  | Year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 |
  |---|---|---|---|---|---|---|---|---|---|
  | Articles | 333 | 329 | 383 | 277 | 474 | 674 | 691 | 786 | 1,102 |

  | Year | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
  |---|---|---|---|---|---|---|---|---|
  | Articles | 1,343 | 1,865 | 1,961 | 1,624 | 2,023 | 2,865 | 3,486 | 4,920 |

  - The total is 25,136.
  - The first count gave 2013 as 276. It missed article 8500, which issue `issue/view/306` links by its public id
    `article/view/1678-1679`, not a number.
- AAAI's `ListSets` is paginated (99 sets on its first page). It lists 386 sets, but only 383 distinct specs (see
  quirk 2).
- **Pre-2010** is not on OJS. The aaai.org library pages redirect to WordPress pages with no abstracts, and
  aaai.org's robots.txt sets `Crawl-delay: 43200`. Milestone B takes AAAI 1980–2008 from the pinned dblp release:
  `conf/aaai/<year>` 1980–2026, with no AAAI in 1981, 1985, 1989, 1995, 2001, 2003 or 2009 (1995 was found by the
  2026-10-10 census; see §AAAI 1980–2008 (dblp)). Its main keys total 28,802,
  and its workshop keys (`2015ethics`, `2017w`, `2021safeai`, …) total 2,368. From 2014 dblp matches OJS closely:
  2026 has 4,920 in both.

### AIES

- 2018–2023 are in the ACM DL. Proceedings DOIs and entry counts:

  | Year | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 |
  |---|---|---|---|---|---|---|
  | DOI | 10.1145/3278721 | 3306618 | 3375627 | 3461702 | 3514094 | 3600211 |
  | Entries | 78 | 91 | 76 | 114 | 115 | 101 |

- From 2024 AIES is on OJS:
  - Vol. 7 (2024, 2 issues): 171 = 150 full archival papers + 20 student abstracts + 1 front matter.
  - Vol. 8 (2025, 4 issues): 279 = 238 main-track papers + 41 student abstracts.
  - AIES 2026 (Malmö, 12–14 Oct 2026) is not yet published.
- **The AIES OAI list is 5 pages of 100, not one response.** An earlier note said "450 records in one response, no
  resumption token"; the live chain on 2026-10-09 had 5 pages.
- Sets: `FUL`, `STU`, `FMT`, `A25-1/2/3`, `A25-SA`, `A25-SA-2`, plus `2025-11` and `ART`, which hold no records.
- The ACM DL is not used for 2018–2023:
  - robots.txt allows `/doi/` with `Crawl-delay: 1`, but every page answered a 403 Cloudflare "Just a moment"
    challenge, with both the research UA and a browser UA.
  - Crossref had no abstract on any of 18 sampled AIES DOIs.
  - aies-conference.com accepted-paper pages give titles and authors only, and the 2022 page is a 404.
  - OpenAlex has abstracts for all 1,025 AIES works, which is the milestone C fallback.
- **Crossref census (2026-10-10; §FAccT, "The ACM census", has the method and the windows).** The six
  proceedings hold 78, 91, 76, 114, 115 and 101 DOIs (575), the entry counts above exactly. All are
  `proceedings-article`s with a title, an author and a `page`; none is a `[[not_paper]]` row, and every one is a
  `main` record. `op ingest crossref` gave each `count_ok: true`.
- **Entries of two pages or fewer: owner review (141; all stay `main` for now).** They fall into three kinds:
  - *Invited or keynote abstracts at the front* (pages 1–7; probably keynotes, which would be `[[not_paper]]`
    rows of kind `keynote` if the owner agrees): 2018 3278721.3278805 (p. 1), .3278806 (p. 2); 2019
    3306618.3314225 (p. 1), .3314261 (pp. 3–4); 2020 3375627.3377142 (pp. 1–2), .3377139 (p. 3), .3377140 (p. 4),
    .3377141 (pp. 5–6), .3375839 (p. 7, in the paper DOI series, so perhaps a paper); 2021 3461702.3462643
    (p. 1), .3462443 (p. 2, five authors, so perhaps a paper); 2022 3514094.3539566–.3539571 (pp. 1–6, six
    single-author entries); 2023 3600211.3607543 (p. 2), .3607544 (pp. 3–4), .3607545 (p. 1).
  - *Student abstracts* (two-page or one-page entries in a block after the papers, nearly all single-author; 2023 .3604760 has three authors): 2018 pp. 354–391 (19
    entries, 3278721.3278783–.3278802); 2019 pp. 521–560 (20 entries, 3306618.3314228 and .3314306–.3314325,
    among them .3314318, whose title is the placeholder "AIES 2019 Student Submission"); 2021 pp. 267–280 (7
    entries, 3461702.3462467–.3462474); 2022 pp. 890–920 (31 one-page entries, 3514094.3539514–.3539564); 2023
    pp. 939–1009 (19 of the entries in that range, 3600211.3604724–.3604764, with longer student entries between
    them).
  - *One-page entries in the paper sequence* (non-archival paper abstracts): 2018 3278721.3278722, .3278723,
    .3278727, .3278746; 2019 3306618.3314227, .3314274; 2020 3375627.3375805, .3375809, .3375816, .3375818,
    .3375819, .3375821, .3375824, .3375853, .3375861, .3375867, .3375869; 2021 3461702.3462520, .3462534,
    .3462537, .3462577, .3462613; 2022 3514094.3534125, .3534151, .3534194.
  Student abstracts from 2024 on are OJS's `student` track (`STU`, `A25-SA`), so the owner may want the same
  track here; the table model has no track column (every Crossref record is `main`, decision-049), so that would
  be a design change, not a row.

### IASEAI

- **IASEAI '25** was the inaugural meeting (Feb 2025, OECD La Muette, Paris). It has no proceedings and no paper
  list (https://www.iaseai.org/our-programs/iaseai25), so there is nothing to index.
- **IASEAI '26** was 24–26 Feb 2026 at UNESCO House, Paris.
  - Proceedings: "Proceedings of IASEAI Conference" Vol. 2 No. 1, AAAI Press, ISBN 978-1-57735-915-9, issue dated
    2026-07-15, https://ojs.aaai.org/index.php/IASEAI/issue/view/741.
  - The front matter (https://ojs.aaai.org/index.php/IASEAI/article/view/43116) says this is the first IASEAI with
    peer-reviewed proceedings: 300 research-paper submissions, double-blind review, **92 accepted research papers**.
  - **57** of them are archival papers on OJS, all in the section "Main Track", plus 1 front matter.
  - OAI: 58 live records + 57 deleted headers, `completeListSize` 115.
  - The other 35 are non-archival and said to be on https://iaseai.org/iaseai26. That page is a client-side app
    with no list found, so they are not indexable now.
- **IASEAI '27** is 9–12 Feb 2027 at UNESCO House, Paris. Submissions closed 2026-10-05 and decisions are due
  2026-11-20.
  - The OpenReview venue `IASEAI.org/2027/Conference` exists, but `public_submissions` is False and 0 notes were
    visible on 2026-10-09.
  - There is no OpenReview group for 2025 or 2026.
- www.iaseai.org's robots.txt allows `/iaseai26`.

## FAccT (milestone B)

The first part of this section is the 2026-10-09 session's record, kept as written. The census of 2026-10-10
(below it) re-read every fact milestone B relies on, with its URL; where the two differ, the census holds.

- 2018 (FAT\*): PMLR v81, 20 entries = 17 papers + a preface + 2 keynotes.
- 2019–2026 are ACM proceedings:

  | Year | DOI | Entries |
  |---|---|---|
  | 2019 | 10.1145/3287560 | 41 |
  | 2020 | 3351095 | 95 (about 27 one-page tutorial or CRAFT entries) |
  | 2021 | 3442188 | 82 |
  | 2022 | 3531146 | 181 |
  | 2023 | 3593013 | 153 |
  | 2024 | 3630106 | 167 |
  | 2025 | 3715275 | 206 |
  | 2026 | 3805689 | 314 (published 2026-06-25) |

- Crossref holds no abstract for any DOI checked. The session recorded "1,341 DOIs", 102 more than the 1,239
  entries above (82 more with the 2018 PMLR volume's 20). The census found no such DOIs (see below).
- facctconference.org: robots.txt allows everything; the 2025 and 2026 final CSVs and the 2022 accepted-papers page
  have abstracts; the other years have titles only (§FAccT site below has the census).
- The ACM DL answers 403 (Cloudflare).
- OpenAlex has abstracts for 100% of 2019–2024, 195 of 206 for 2025, and 293 of 317 for 2026 *(query not
  recorded; unverified here; milestone C re-reads it)*. Its DOIs are sometimes truncated or duplicated, which is
  the likely reason its 2026 count (317) differs from the 314 Crossref DOIs.
- ACM has been fully open access since 2026-01-01. No metadata or abstract licence was found.

### The ACM census (2026-10-10)

`scripts/acm_census.py` drives the miner's own Crossref route (`crawl.crossref_fetcher`, `crossref.harvest`), one
request at a time, so the pages it caches are the ones `op ingest crossref` replays. Per proceedings DOI it read the
proceedings record (`/works/<doi>`), walked `prefix:10.1145` over a wide window (the record's `published` date ±120
days, 21–34 cursor pages of 1,000 works each), kept every DOI extending `10.1145/<toc>.`, and read
`works?filter=prefix:10.1145,isbn:<isbn>&rows=0`. Its output drafted the 14 `[[proceedings]]` rows of
`ingest/acm_proceedings.toml`.

| Venue-year | Proceedings DOI | `published` | Wide-window works | DOIs (`dois`) | Not-paper rows | Records | Window |
|---|---|---|---|---|---|---|---|
| FAccT 2019 | 10.1145/3287560 | 2019-01-29 | 20,822 | 41 | 0 | 41 | 2019-01-22 – 02-05 |
| FAccT 2020 | 10.1145/3351095 | 2020-01-27 | 19,506 | 95 | 26 | 69 | 2020-01-20 – 02-03 |
| FAccT 2021 | 10.1145/3442188 | 2021-03 (month only) | 20,719 | 82 | 0 | 82 | 2021-02-22 – 03-08 |
| FAccT 2022 | 10.1145/3531146 | 2022-06-20 | 23,233 | 181 | 0 | 181 | 2022-06-13 – 06-27 |
| FAccT 2023 | 10.1145/3593013 | 2023-06-12 | 23,164 | 153 | 0 | 153 | 2023-06-05 – 06-19 |
| FAccT 2024 | 10.1145/3630106 | 2024-06-03 | 27,998 | 167 | 0 | 167 | 2024-05-27 – 06-10 |
| FAccT 2025 | 10.1145/3715275 | 2025-06-23 | 29,611 | 206 | 0 | 206 | 2025-06-16 – 06-30 |
| FAccT 2026 | 10.1145/3805689 | 2026-06-25 | 32,149 | 314 | 0 | 314 | 2026-06-18 – 07-02 |
| AIES 2018 | 10.1145/3278721 | 2018-12-27 | 19,515 | 78 | 0 | 78 | 2018-12-20 – 2019-01-03 |
| AIES 2019 | 10.1145/3306618 | 2019-01-27 | 20,817 | 91 | 0 | 91 | 2019-01-20 – 02-03 |
| AIES 2020 | 10.1145/3375627 | 2020-02-07 | 19,735 | 76 | 0 | 76 | 2020-01-31 – 02-14 |
| AIES 2021 | 10.1145/3461702 | 2021-07-21 | 26,675 | 114 | 0 | 114 | 2021-07-14 – 07-28 |
| AIES 2022 | 10.1145/3514094 | 2022-07-26 | 26,057 | 115 | 0 | 115 | 2022-07-19 – 08-02 |
| AIES 2023 | 10.1145/3600211 | 2023-08-08 | 30,554 | 101 | 0 | 101 | 2023-08-01 – 08-15 |

- **Totals:** FAccT 2019–2026 1,239 DOIs, 1,213 records (plus 17 from PMLR v81); AIES 2018–2023 575 DOIs, 575
  records. Every count equals the 2026-10-09 entry count, so no row needed a correction. The session's "1,341
  DOIs" is not reproduced: no DOI outside the 1,239 extends a FAccT toc anywhere in the ±120-day windows. The 102
  were most likely another route's duplicates (OpenAlex's truncated or repeated DOIs); the session did not record
  them.
- **The windows.** Every DOI of a proceedings carries the proceedings' own `published` date (one date per
  proceedings, all 14; FAccT 2021's is month precision only, `[2021, 3]`, read as 2021-03-01), so the rule `min(published) − 7 days … max(published) + 7 days` gives a 15-day window
  centred on that date. `op ingest crossref` over those windows (2–5 cursor pages each) found exactly the DOIs the
  wide windows found: 14 listings, each `count_ok: true`.
- **No DOI lacks a field the miner needs.** Every work is a `proceedings-article`, every one has a title, at least
  one author (`no_authors` 0 in all 14) and a `page` value.
- **The ISBN route is no cross-check.** `works?filter=prefix:10.1145,isbn:<isbn>` answers `total-results` 1 for all
  14 ISBNs: only the proceedings record carries the ISBN, and the papers carry none (checked on
  `/works/10.1145/3287560.3287581`, which has `container-title` and `event` but no `ISBN`). Crossref offers no exact
  filter on `container-title`, and its `query.*` parameters score rather than filter. The independent checks are
  therefore: (1) every census count equals the 2026-10-09 session's entry count, which came by another route; (2)
  the 206 FAccT 2025 DOIs are exactly the 206 `10.1145/3715275.` DOIs in the conference's own 2025 CSV (both ways);
  (3) the 2022 accepted-papers page links 180 of the 181 FAccT 2022 DOIs (§FAccT site); (4) the narrow and wide
  windows agree. A DOI with no publication date at all would be outside every window; none of the 1,814 lacks one,
  but a proceedings DOI deposited without dates later could only be caught by the count check.
- **Official counts:** none gated. No FAccT or AIES 2018–2023 statement of an accepted-paper count was read, and
  the census counts are the proceedings' own contents (archival papers plus, for FAccT 2020, tutorials and CRAFT
  sessions), which an official "accepted papers" figure would not define the same way. So no `official_counts.py`
  row is added (spec 07 §C).

### FAccT 2020: the tutorial and CRAFT rows

FAccT 2020 (FAT\* 2020) has 95 DOIs. Pages 1–680 are the papers (a few of them one-page non-archival abstracts in the
paper sequence, such as page 680, "Measuring justice in machine learning", which the 2020 accepted-papers page
lists). After them come two blocks of one-page entries, each roughly alphabetical by title:
- **pages 681–695, 14 CRAFT sessions** (DOIs 3375680–3375697; there is no page 694 entry). Every title is a CRAFT
  session in https://facctconference.org/2020/programschedule.html (a `craft` cell or a link to
  `acceptedcraftsessions.html`).
- **pages 696–707, 12 tutorials** (DOIs 3375662–3375673). Nine titles end "hands-on tutorial", "translation
  tutorial" or "implications tutorial". The other three (3375665 "Leap of FATE…", 3375668 "Policy 101…", 3375671
  "The meaning and measurement of bias…") are tutorials on https://facctconference.org/2020/acceptedtuts.html and
  the schedule ("Translation Tutorial").

These 26 are `[[not_paper]]` rows (12 `tutorial`, 14 `craft session`); the 2026-10-09 "about 27" was an estimate.
The 2020 schedule also lists two CRAFT sessions with no DOI ("Rump Session: CRAFT on Speed", "Infrastructures:
Mathematical Choices and Truth in Data"), and Crossref has no tutorial for "What does 'fairness' mean in (data
protection) law?" or "Gender: what the GDPR does not tell us"; they are no records either way.

**Left as papers, for owner review** (one-page entries in a paper sequence: non-archival abstracts, not keynotes
or front matter):
- FAccT 2019: 3287560.3287581 (p. 139), .3287582 (p. 180), .3287593 (p. 89).
- FAccT 2020: 3351095.3372825 (p. 581), .3372838 (p. 680), .3373153 (p. 32), .3373154 (p. 110), .3373155
  (p. 546), .3373156 (p. 413), .3373157 (p. 294), .3375674 (p. 513). The five checked ("Measuring justice", "What's
  sex got to do with machine learning?", "Dirichlet uncertainty wrappers…", "Algorithmic accountability in public
  administration: the GDPR paradox", "The social lives of generative adversarial networks") are on the 2020
  accepted-papers page.
- FAccT 2021: 3442188.3445864 (p. 2), .3445866 (p. 14), .3445889 (p. 261), .3445891 (p. 272), .3445893 (p. 284),
  .3445926 (p. 647), .3445929 (p. 1, "Black Feminist Musings on Algorithmic Oppression", one author: a paper, but
  first in the proceedings), .3445942 (p. 816).
- FAccT 2022: 3531146.3533087, .3533123, .3533126, .3533152, .3533162, .3533167, .3533215 (one page each).
- FAccT 2023: 3593013.3593970 (p. 1, four authors), .3593993, .3594014, .3594017, .3594027, .3594030, .3594035,
  .3594055, .3594123 (one page each).
- FAccT 2024–2026: no entry of one page, and no title starting Tutorial, CRAFT, Keynote or Panel.

### PMLR v81 (FAccT 2018)

Read once on 2026-10-10 (https://proceedings.mlr.press/v81/; recorded as
`backend/tests/fixtures/http/pmlr/v81/volume-index.json`). The heading reads "Volume 81: Conference on Fairness,
Accountability and Transparency, 23-24 February 2018, New York, NY, USA"; the PMLR index (https://proceedings.mlr.press/)
names it "FAT\* 2018 Proceedings". 20 `<div class="paper">` entries, every one with an `abs` link: the preface
(`friedler18a`, the two editors), "Keynote 1" (`sweeney18a`) and "Keynote 2" (`hellman18a`), then 17 contributed
papers. The `pmlr_volumes.toml` row: `papers = 20`, `not_papers = ["friedler18a", "sweeney18a", "hellman18a"]`.
`op ingest pmlr --venue FAccT --year 2018` gave v81 `count_ok: true`, listed 20, 17 records, `skipped:
{"not_paper": 3}`.

## FAccT site (facctconference.org, 2026-10-10)

Read once each through a `facctconference.org` fetcher (`expect="text"`), cached under `<data>/cache/facct_site`,
and recorded (scrubbed, trimmed) under `backend/tests/fixtures/http/facct_site/`.

- **robots.txt** (https://facctconference.org/robots.txt): `User-agent: *` with an empty `Disallow:`, and a
  sitemap line. Everything is allowed.
- **2025 final CSV** (https://facctconference.org/static/docs/facct2025-final.csv), served as
  `application/octet-stream`, no byte-order mark, `\r\n` row ends (217 of them, and a few bare `\n` inside quoted
  fields; the census's first reading said `\n`, corrected by Task 10). Columns `TYPE, ID, ABSTRACT, AUTHOR, TITLE, URL,
  URL-OLD`. **217 rows** = 206 `archival` + 11 `nonarchival`; `ID` distinct; every row has an abstract. **206 rows
  have a `10.1145/3715275.` DOI in `URL`** (`https://doi.org/…`), exactly the archival rows, and exactly the 206
  Crossref DOIs. The 11 non-archival rows have an arXiv, SSRN or empty `URL` (5 empty). `AUTHOR` is BibTeX style,
  `Last, First and Last, First`.
- **2026 final CSV** (https://facctconference.org/static/docs/facct2026-final.csv), also
  `application/octet-stream`, no byte-order mark, `\n` line ends. Columns `Paper ID, Title, Authors, Abstract` (no
  type, no DOI). **325 rows**, `Paper ID` distinct, every abstract present; `Authors` are `;`-separated. 325 − 314 =
  **11 rows are expected to stay unmatched** (non-archival, by the same pattern as 2025; the CSV does not mark
  them). An exact title join (case and punctuation folded) leaves 27 rows unmatched, so about 16 archival titles are
  worded differently between the CSV and Crossref; in 2025 the same join leaves 16 (11 non-archival + 5 worded
  differently). Task 10's title join must expect this.
- **2022 accepted papers** (https://facctconference.org/2022/acceptedpapers.html), `text/html`. **181 entries**, as
  many as the Crossref DOIs. The structure Task 10's `facct2022_html` parser reads: inside `<div class="container">
  <div class="row"> <div class="col-lg-12">`, each entry is a run of siblings, starting at an `<h4 id="N">`:
  - `<h4 id="N"><b>TITLE</b></h4>`. The id is a number, distinct per entry; its attribute is written `id="N"`,
    `id ="N"` or `id = "N"` (13 entries use a spaced form);
  - an optional `<h5>` award line (4 entries, e.g. "Co-Winner: Distinguished Paper Award");
  - `<p><i>AUTHORS</i></p>` and a `<br>` (authors comma-separated, the last joined by "and");
  - `<p>ABSTRACT</p>`, one paragraph in every entry;
  - `<p><span class="label label-primary"><a href="https://doi.org/10.1145/3531146.N">Paper</a></span></p>`, then a
    `Video` label of the same form.
  Every entry has exactly one `Paper` DOI link, but they name 180 distinct DOIs: "Seeing without Looking: Analysis
  Pipeline for Child Sexual Abuse Datasets" (`id="295"`) links 3531146.3533138, which is "Robots Enact Malignant
  Stereotypes" (`id="314"`); its own DOI, 3531146.3534636, is linked nowhere. A DOI join would mis-attach that
  abstract, which is why the 2022 join is by title. An exact title join leaves 12 of the 181 unmatched (11 wording
  differences, found in the census, and one token-contract case found when the join was built: "Pareto-Improving
  Data-Sharing" has `∗` (U+2217) on the page and `✱` (U+2731) in Crossref, and the token contract keeps the first as
  the token `ast` and drops the second, where the census's case-and-punctuation fold dropped both). The recorded fixture keeps 20 entries, among them ids 295 and 314, an `<h5>` entry and the spaced id
  form `id = "17"`.

## AAAI 1980–2008 (dblp)

Read 2026-10-10 from the pinned release `10.4230/dblp.xml.2026-10-03` (sha256 `20e45961…e969`, already on disk;
nothing was fetched) by `scripts/dblp_aaai_census.py`. The census wrote only AAAI's extract
(`<cache>/dblp/extract/aaai/<sha256>.json`). ICML's extract hashed
`c2086904b5ac1783ee4cf58877512b60d5e42e1199150bd8d4fc1979be2e0168` before and after (unchanged; guarantee 4).
`backend/src/openproceedings/ingest/dblp_aaai.toml` holds the rows below.

**Not held.** The release has no `conf/aaai/` proceedings key dated 1981, 1985, 1989, **1995**, 2001, 2003 or 2009.
The design and the milestone B plan listed six years and missed 1995. The meetings' ordinals in dblp's own titles
settle it: 1994 is the 12th National Conference and 1996 the 13th (IJCAI-95 met in Montreal). So `not_held` has
seven years, and AAAI 1980–2008 has 23 held years, not 24.

**Per-year counts.** `papers` is the inproceedings crossref'ing the year's main key(s), not-paper rows included.
Records = papers − not-paper rows + workshop papers.

| Year | Main key(s) | Main papers | Not-paper rows | Workshop papers | Records |
|---|---|---|---|---|---|
| 1980 | `1980` | 95 | | | 95 |
| 1982 | `1982` | 104 | | | 104 |
| 1983 | `1983` | 92 | | | 92 |
| 1984 | `1984` | 69 | | | 69 |
| 1986 | `1986-1` (120), `1986-2` (79) | 199 | 11 | | 188 |
| 1987 | `1987` | 149 | | | 149 |
| 1988 | `1988` | 150 | | | 150 |
| 1990 | `1990` | 174 | 1 | | 173 |
| 1991 | `1991-1` (80), `1991-2` (64) | 144 | | | 144 |
| 1992 | `1992` | 134 | | | 134 |
| 1993 | `1993` | 135 | | | 135 |
| 1994 | `1994-1` (129), `1994-2` (173) | 302 | | | 302 |
| 1996 | `1996-1` (132), `1996-2` (157) | 289 | | 16 (`1996w1`) | 305 |
| 1997 | `1997` | 213 | | 37 (`1997ca` 24, `1997w6` 13) | 250 |
| 1998 | `1998` | 206 | | | 206 |
| 1999 | `1999` | 193 | | | 193 |
| 2000 | `2000` | 233 | | | 233 |
| 2002 | `2002` | 180 | | | 180 |
| 2004 | `2004` | 194 | | | 194 |
| 2005 | `2005` | 325 | | | 325 |
| 2006 | `2006` | 385 | | | 385 |
| 2007 | `2007` | 368 | | | 368 |
| 2008 | `2008` | 356 | | | 356 |
| **Total** | | **4,689** | **12** | **53** | **4,730** |

All keys are `conf/aaai/…`. The four split years (1986, 1991, 1994, 1996) each have two volumes, as the design
said; 1990's single key is titled "2 Volumes". `op ingest dblp --venue AAAI --year 1980-2008` printed 23 listings, every
one `count_ok: true`, and `not_held: [1981, 1985, 1989, 1995, 2001, 2003]` (2009 is outside the asked range).

**Workshops.** These three keys are each titled "(Collected) Papers from the 1996/1997 AAAI Workshop", and their papers
are track `workshop`:
- `conf/aaai/1996w1`, Agent Modeling (1996): 16 papers;
- `conf/aaai/1997ca`, Constraints & Agents (1997): 24 papers;
- `conf/aaai/1997w6`, Deep Blue Versus Kasparov (1997): 13 papers.

**Excluded.** `conf/aaai/1991w` is excluded. It is *Intelligent Multimedia Interfaces*, which dblp dates 1993. Its
title calls it "an outgrowth of the AAAI Workshop on Intelligent Multimedia Interfaces, Anaheim, 1991". That makes it
an edited book, not the workshop's proceedings, and reading it as a workshop would file 1991 work under AAAI 1993.
It holds 16 inproceedings, and the 1991 listing counts them under `excluded_proceedings`. No other `conf/aaai/`
proceedings key is dated 1980–2009, and none lacks a year.

**Not-paper rows** (12; counted in their year's listing, never records). Each title says what it is:

| Key (`conf/aaai/…`) | Year | Kind | Why |
|---|---|---|---|
| `Darden86` | 1986 | invited talk | "Invited Talk: …", pp. 1146–1147 |
| `Hendrix86` | 1986 | invited talk | "Invited Talk: …", p. 1148 |
| `McDermottH86` | 1986 | panel | "… (Panel)", p. 1149 |
| `SolowayBMRS86`, `Winston86`, `FriedlandMS86`, `HartGRW86`, `AikinsHMSS86`, `FehlingAAGLM86` | 1986 | panel | "Panel: …" / "President's Panel: …", all p. 1150 |
| `KaczmarekNBHMWWW86` | 1986 | panel | "Panel: …", p. 1151 |
| `NechesFKMP86` | 1986 | panel | "Panel: …", p. 1153 |
| `Dumais90` | 1990 | panel | "Panel: User Modeling and User Interfaces", the chair's two-page introduction |

The census's title pattern also matched `LesperanceL90` ("Indexical Knowledge…") and `Domeshek91` ("Indexing
Stories…"). Both are papers, and both stay papers. No entry under a main or workshop key lacks an author.

**For owner review** (left as papers). Each of these may be a talk or panel abstract, but its title doesn't say so
clearly enough to drop it:
- One-page "(Abstract)" entries that read like invited-talk abstracts:
  - `Feigenbaum93`, "Tiger in a Cage … (1993) - Abstract", p. 852;
  - `Simon93`, "Artificial Intelligence as an Experimental Science (Abstract)", p. 853;
  - `Abarbanel96`, "The BOEING 777 … (Abstract)", p. 1589;
  - `Wellman97`, "Market-Oriented Programming (Abstract)", p. 774;
  - `ArkinF97`, "The AAAI-97 Mobile Robot Competion … (Abstract)", p. 755.
  ICML's table marks entries of this shape as invited talks, but AAAI's titles don't name them as talks.
- `SelmanBDHMN96`, "Challenge Problems for Artificial Intelligence (Panel Statements)", pp. 1340–1345: six pages of
  panelists' statements.
- The 1990 panelists' short statements:
  - `Hollan90`, `McKeown90` and `Jones90` follow `Dumais90`'s user-modeling panel, pp. 1137–1141;
  - `Balzer90`, `Fikes90`, `Fox90`, `McDermott90` and `Soloway90` are an AI-and-software-engineering set, pp. 1123–1134.
- `conf/aaai/1991w`: the owner may prefer to read it as a 1991 workshop rather than exclude it. The table can't file
  it under 1991, because dblp dates the key 1993.
- One-page video and demonstration abstracts, such as 1993 pp. 856–857 and 1994 pp. 1506–1507. They are short
  entries of a non-paper program, but each describes a system and has authors.

**IAAI cross-check.** `gzip -dc … | grep -o '<crossref>conf/aaai/[^<]*</crossref>' | sort | uniq -c` gives, for every
`conf/aaai/` key dated 1980–2008, exactly the census's `conf/aaai/`-keyed count. So the difference is **0 in every
year**: no record keyed outside `conf/aaai/` (`conf/iaai/…`) crossrefs an AAAI volume before 2009. The volumes from
1996 on name IAAI in their titles, but this release crossrefs no IAAI paper to them (the design's §Sources 2: IAAI
has its own proceedings before 2010; `conf/iaai/` was not read here). IAAI before 2010 stays out of scope by design.

**Other counts** (over the 4,758 inproceedings under keys dated 1980–2009):
- 678 author occurrences (326 distinct names) carry a dblp homonym number, which `clean_author` drops.
- No key fails `dblp.NATIVE`.
- No entry has a `publtype`.
- **No entry has a DOI `ee`**, so every AAAI 1980–2008 record has `urls.doi` empty. Milestone C's OpenAlex fill
  must match these records by title.
- No inproceedings dated 1980–2009 crossrefs a missing proceedings key.

## Licence posture

What each source states about reuse, and what the index does with its text. None of this is legal advice; the
project's position is decision-018 (README §Abstracts on a public instance).

| Source | Stated licence | Checked |
|---|---|---|
| ojs.aaai.org (AAAI, AIES, IASEAI) | `dc:rights` "Copyright (c) <year> …"; no open licence | 2026-10-09, in every record read |
| ACM DL (FAccT 2019–2026) | none found for metadata or abstracts (the DL answers 403; ACM is open access since 2026-01-01, which covers the papers, not a metadata licence) | 2026-10-09 |
| facctconference.org CSVs | none found | 2026-10-09 *(page not recorded; unverified here)* |
| OpenAlex (milestone C fallback) | not checked in this task (OpenAlex documents its data as CC0; re-check before milestone C stores any abstract) | not checked |
| Crossref | not checked in this task (it holds no FAccT abstract, so none would be taken from it) | not checked |
| the pinned dblp release | not checked in this task; decision-047 covers it (titles, no abstracts) | not checked |

**Index versus fixtures.** The live index stores and shows an OJS abstract with its attribution ("AAAI Digital
Library") and a link to the paper's own page on ojs.aaai.org, never the full text, on decision-018's fair-dealing
basis, as for the other non-CC sources. Committed test fixtures are different: their titles, authors and abstracts
are synthetic (decision-004), so no copyrighted text is in the repository.

## The census: how it was taken

`scripts/ojs_section_census.py` drives the miner's own harvest (`ojs_harvest.harvest_journal`) through `crawl.ojs_fetcher`.
The pages it caches are therefore the ones `op ingest ojs` replays. A journal is harvested in three steps:
1. **Inventory:** the journal-wide `ListIdentifiers` chain (AAAI: 53 pages of 500). It is the source of truth for
   which articles exist and which are deleted.
2. **Sets:** every set's `ListRecords` chain (`set=<spec>`) supplies the metadata in bulk. Inside a set, a page
   that answers HTTP 5xx after every retry falls back to the set's `ListIdentifiers` plus `GetRecord`.
3. **Gaps:** every live inventory article that no set returned is read by `GetRecord`.

The AAAI harvest read 589 OAI pages, IASEAI 5 and AIES 12, plus the `ListSets` pages.

## Reconciliation

| Journal | completeListSize | Live | Unavailable | Deleted headers | Live + unavailable + deleted |
|---|---|---|---|---|---|
| AAAI | 26,185 | 25,136 | 1 (39173) | 1,048 | 26,185 |
| AIES | 450 | 450 | 0 | 0 | 450 |
| IASEAI | 115 | 58 | 0 | 57 | 115 |

- **The ~1,050-record AAAI gap** between `completeListSize` (26,185) and the issue pages is fully explained.
  - It consists of deleted headers: 1,048 headers over 449 distinct ids.
  - 448 of those ids are articles that are also live: each re-published article left 1–6 stale tombstones. For
    example, articles 8098–8100 (`AAAI:AIW`) are live with datestamp 2021-10-04, and each has 3–5 deleted headers
    dated 2021-09-20.
  - The 449th is `oai:ojs.pkp.sfu.ca:article/5828` (`AAAI:ML`, datestamp 2020-06-02), a pre-2020 identifier from
    the old repository. Such an identifier is accepted on a deleted header only.
- **The remaining difference is +1.** AAAI's live total (25,136 + 1 unavailable = 25,137) is one more than the
  corrected issue-page total of 25,136. The extra one is article 39173, which is on no issue page: 2026's other
  records alone add up to the issue pages' 4,920.
- **Per volume**, every AAAI volume's live count equals its issue-page count, front matter included (`AAAI:FRNT`,
  8 records in 2013; `AAAI:Errata`, 2 in 2023). 2026 is 4,920 live records plus 39173.
- **The front matter in AIES 2024 (1) and IASEAI 2026 (1)** is listed in OJS. The table counts it as front matter,
  never as a record.

`op ingest ojs --offline` on the cache: 20 listings (AAAI 2010–2026, AIES 2024–2025, IASEAI 2026), every one
`count_ok`. The journals (after the owner ruled AAAI 2023's two Errata front matter; the first run read AAAI
25,128 records and 8 front matter):

| Journal | Records | Deleted | Front matter | Unavailable | Duplicates | Recovered by GetRecord |
|---|---|---|---|---|---|---|
| AAAI | 25,126 | 1,048 | 10 | 1 | 19 | 5 |
| AIES | 449 | 0 | 1 | 0 | 0 | 0 |
| IASEAI | 57 | 57 | 1 | 0 | 0 | 0 |

The "Recovered by GetRecord" column counts live inventory articles that no set returned; quirk 2 explains them.

## Two server quirks (what the harvest design answers)

1. **One unrenderable article breaks a whole page.**
   - Article 39173 (set `AAAI:APP`, "AAAI Technical Track: Applications", datestamp 2026-03-14) answers HTTP 500:
     - in `GetRecord` in every format (`oai_dc`, `marcxml`, `rfc1807`);
     - on its article page;
     - on any `ListRecords` page that holds it. That was cursor 23,400 of the journal-wide chain and page 3 of the
       `APP` set chain. The response is an empty body in about 0.8 s, every time, over several hours.
   - It is listed live by `ListIdentifiers`, which is not affected. Ids 39129–39172 do not exist. Most likely it is
     an article attached to no issue.
   - A failed page carries no next token. A journal-wide chain therefore lost everything after it: 2,785 records of
     2026.
   - **Crossref does not have it.** `10.1609/aaai.v40i24.39173` and `…v40i25.39173` (the issues of its neighbours
     39128 and 39174) both answer 404, and `works?filter=prefix:10.1609&query=39173` returns only an unrelated work.
   - **Nor does dblp, and it is no published paper.** The pinned dblp release (`10.4230/dblp.xml.2026-10-03`) lists
     exactly 4,920 `10.1609/aaai.v40i…` DOIs, the AAAI 2026 issue pages' count, and none is 39173. A retry on
     2026-10-10 still answered HTTP 500 for GetRecord and the article page. So 39173 is a broken OAI entry, not a
     missing paper: every published AAAI 2026 paper is indexed. The `[[unavailable]]` row names it so the crawl
     notices if the server ever serves it (`stale_unavailable_row`).
   - It is named in an `[[unavailable]]` row: volume 40 (inferred from its id and datestamp), counted in 2026's
     stated total (4,921 = 4,920 + 1) and never a record. A follow-up task tracks it.
2. **Set names are not unique, and the server's `set=` filter matches case-blind to one section.**
   - AAAI's `ListSets` lists `AAAI:EAAI-POS` twice ("EAAI Poster Papers", "EAAI Symposium Poster Paper") and
     `AAAI:EAAI-FP` twice (both "EAAI Symposium: Full Papers"). It also lists `AAAI:EAAI-Full` ("EAAI Full Papers")
     alongside `AAAI:EAAI-FULL` ("EAAI Symposium Full Paper").
   - `set=AAAI:EAAI-Full` returns the 19 `EAAI-FULL` records, which is where the 19 duplicates come from. Its own 3
     records (19039–19041) are never returned.
   - `set=AAAI:EAAI-POS` returns 10 of the spec's 12 records. 19042–19043 belong to the other section.
   - These 5 papers (all 2014 EAAI) come only from the inventory plus `GetRecord`.
   - The duplicate copies were identical. The miner keeps one copy and counts the rest under `duplicates`, never in
     `listed`; two copies that differed would stop the crawl.
   - Each shared spec sits in different volumes, so (journal, volume, set) rows still tell them apart:
     - `EAAI-Full` is v28; `EAAI-FULL` is v30–31.
     - `EAAI-POS` is v28 (2 records) and v30–31.
     - `EAAI-FP` is v35 and v36.
   - The two `EAAI-POS` names can't be matched to their volumes from OAI. That row's label keeps both names.

## Section → track mapping (the table)

Following the design's Tracks table, the 601 section rows break down as follows. Rows are counted per (journal,
volume, set), so a set used in several years has one row per year.

| Track | Rows | Sections |
|---|---|---|
| `main` | 402 | AAAI technical tracks; "Technical Papers: …"; "Main Track: …"; "Main Technical Papers"; topic sections of 2010–2014 (Robotics, Knowledge Representation and Reasoning, …); special tracks (AI for Social Impact, Safe/Robust/Responsible AI, AI Alignment, the 2021 focus areas, the 2010–2016 special tracks, and the 2011 and 2013 "Robotics Program", AAAI-13's AI and Robotics special track); Journal Track; AIES full papers and main tracks; IASEAI Main Track |
| `student_abstract` | 20 | Student abstracts, including "Pre-PhD Student Abstracts" (2013) |
| `consortium` | 20 | Doctoral and undergraduate consortia |
| `demo` | 13 | Demonstrations, including "Virtual Agent Demonstrations" (2015) |
| `iaai` | 53 | IAAI sections |
| `eaai` | 52 | EAAI sections |
| `other` | 37 | Senior Member papers and presentations; "Senior Track" (2018); New Faculty Highlights; Emerging Trends; the owner-decision rows below (NECTAR, What's Hot, Sister Conference, Spotlight) |
| `front_matter` | 4 | AAAI 2013 "Frontmatter"; AAAI 2023 "Errata" (errata notices, not papers; the owner ruled front matter); AIES 2024 and IASEAI 2026 "Frontmatter" |

The `main` and `student_abstract` rows include AIES (4 main, 3 student-abstract rows) and IASEAI (1 main row).

Per year, AAAI's `main` count is:

| Year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 |
|---|---|---|---|---|---|---|---|---|---|
| `main` | 262 | 248 | 294 | 202 | 398 | 538 | 548 | 639 | 937 |

| Year | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|
| `main` | 1,147 | 1,610 | 1,694 | 1,369 | 1,720 | 2,542 | 3,189 | 4,475 |

The 2026 `main` figure is 4,475 records; the table's 4,476 includes the unavailable article 39173. The miner enforces
counts per volume, not per section, so a record that moves between sections within a volume is not caught by the
count check.

### Owner decisions on the sections the mapping doesn't name (2026-10-10, TASK-218)

The design's mapping doesn't name these sections, so they were first mapped to `other` and put to the owner. The owner
decided each on 2026-10-10. `AAAI:ROBOT` ("Robotics Program", 2011 and 2013) had already moved to `main`: AAAI's official
2013 count of 203 includes it as a special track (§Official counts). `AAAI:Errata` (2023, 2 notices) became front
matter by the controller's ruling (errata are no papers), so it is no record.

| Section | Years | Papers | Decision | Why |
|---|---|---|---|---|
| `AAAI:SHORT` "Short Papers" | 2010 | 3 | **main** | refereed, original AAAI-10 technical papers, only shorter |
| `AAAI:NECTAR` "New Scientific and Technical Advances in Research" | 2010, 2011 | 12 + 12 | other | digests of papers published at other venues |
| `AAAI:HOT` "What's Hot Abstracts" | 2015–2017 | 8 + 9 + 7 | other | summaries of hot topics at other venues |
| `AAAI:SIS` "Sister Conference Track" | 2020 | 15 | other | digests of papers from sister conferences |
| `AAAI:SPOT` "Spotlight" | 2012 | 17 | other | content unconfirmed (likely sub-area overview talks); revisit if the AAAI-12 programme shows otherwise |

The "why" column is the owner's rationale. For NECTAR, What's Hot and Sister Conference it follows from the section
names (inferred from the title; no section page or programme is recorded as opened here), and SPOT's content is
unconfirmed. The only section labels checked against the live site are the two TASK-221 read (`AAAI:AI24-43`,
`AIES:A25-SA`).

Re-presented work stays out of the default search so it doesn't sit beside its original and inflate AAAI hit counts;
`track:other` brings it back. Each row carries an "owner decision" comment in `ojs_sections.toml`.

## Official counts (spec 07 §C)

Six rows were added to `official_counts.py` and `docs/results/coverage-sources.md` (TASK-219, read 2026-10-09 by
plain GETs of the pages named; dblp.org never fetched). Classes: **gateable** (an official statement whose
definition is our `main` cell, within ±1%), **definition mismatch**, **not found** (aggregator or news figures
exist for some years; they are never a row). "Ours" is the `main` cell after the Robotics Program move (the
2026-10-10 coverage report's figure, plus the moved rows for 2011 and 2013).

| Venue-year | Official | What it counts | Source | Ours | Class |
|---|---|---|---|---|---|
| AIES 2024 | 150 | archival full papers accepted (468 reviewed); student abstracts separate | https://ojs.aaai.org/index.php/AIES/article/view/31763 (chairs' front matter); the table in https://www.aies-conference.com/2025/wp-content/doc/AIES-2025-Program-10.20.pdf | 150 | gateable (row) |
| AIES 2025 | 238 | archival full papers accepted (748 reviewed); student abstracts separate | https://www.aies-conference.com/2025/wp-content/doc/AIES-2025-Program-10.20.pdf | 238 | gateable (row) |
| AAAI 2013 | 203 | technical program incl. the four special tracks (AI and the Web, Cognitive Systems, Computational Sustainability, AI and Robotics); late-breaking and spotlights excluded | https://ojs.aaai.org/index.php/AAAI/article/view/8512 (AAAI-13 preface) | 202 | gateable (row) once "Robotics Program" is `main` (it was a mismatch at 191) |
| AAAI 2015 | 539 | papers "selected … and presented" from the main technical and topical tracks (AI Magazine report) | https://ojs.aaai.org/index.php/aimagazine/article/view/2606/2500 | 538 | gateable (row; the weakest wording) |
| AAAI 2018 | 938 | original research publications in the proceedings (3,800 submissions) | https://ojs.aaai.org/index.php/AAAI/issue/view/301 | 937 | gateable (row) |
| AAAI 2019 | 1,147 | original research publications in the proceedings (7,095 submissions) | https://ojs.aaai.org/index.php/AAAI/issue/view/246 | 1,147 | gateable (row) |
| AAAI 2014, 2016, 2017 | none | submissions only (1,406; 2,132; 2,571) | issue pages 305, 303, 302 | 398, 548, 639 | not found |
| AAAI 2010–2012, 2020–2026 | none | no AAAI statement found (aggregator figures only) | issue pages; aaai.org conference pages | see the per-year table | not found |
| IASEAI 2026 | 92 | accepted research papers, 35 of them non-archival and unpublished on OJS | https://ojs.aaai.org/index.php/IASEAI/issue/view/741 | 57 | definition mismatch: recorded, not gated |

- **AIES.** The chairs' statements are not the OJS issue listing (whose totals this note once called circular);
  the 2025 program is on the conference's own site. Whether "accepted" is before or after withdrawals is not
  stated; the exact match with the listing suggests none.
- **AAAI 2018, 2019.** "Original research publications" is read as the technical program, special tracks
  included; the front matter does not itemise.
- **AAAI 2020–2026.** The trackers' figures sit close to our `main` minus the special tracks and Journal Track, so
  they likely count the Main Technical Track only; even an official figure of that kind would be a definition
  mismatch with our `main`. The chairs' opening slides or AAAI press releases may hold the official numbers.
- **FAccT 2018–2026 and AIES 2018–2023 (2026-10-10): none gated, no row.** The census counts are the proceedings'
  contents (Crossref's DOIs, PMLR's index), and no official accepted-paper statement was read for these years.
  FAccT's site gives accepted-paper lists, not a stated count, and the 2025/2026 lists include non-archival papers
  the proceedings don't (217 and 325 rows against 206 and 314 DOIs), so even a stated figure would likely be a
  definition mismatch with our `main` (§FAccT, "The ACM census").

## Sources checked

- https://ojs.aaai.org/robots.txt
- https://ojs.aaai.org/index.php/AAAI/oai (and AIES, IASEAI), with the verbs ListSets, ListIdentifiers, ListRecords
  and GetRecord
- AAAI issue 306 (2013)
- https://ojs.aaai.org/index.php/IASEAI/issue/view/741 and article/view/43116
- for the official counts (2026-10-09): AAAI issue pages 246, 301–310, the AAAI-13 preface (article/view/8512), the
  AI Magazine AAAI-15 report (aimagazine/article/view/2606), the AIES 2024 front matter (AIES/article/view/31763),
  the AIES 2025 program (aies-conference.com), and the aaai.org AAAI-10 to AAAI-26 conference pages
- https://api.crossref.org/works/10.1609/aaai.v40i24.39173 and the v40i25 DOI
- `api.crossref.org/works?filter=prefix:10.1609&query=39173`
- iaseai.org (IASEAI '25, '26, '27 pages)
- OpenReview `IASEAI.org/2027/Conference`
- dl.acm.org (403)
- facctconference.org (2026-10-10: robots.txt, 2020/index.html, 2020/acceptedtuts.html, 2020/programschedule.html,
  2020/acceptedpapers.html, 2022/acceptedpapers.html, static/docs/facct2025-final.csv, static/docs/facct2026-final.csv)
- api.crossref.org (2026-10-10): `/works/<doi>` for the 14 ACM proceedings DOIs; `/works?filter=prefix:10.1145,
  from-pub-date:…,until-pub-date:…` cursor chains (wide and narrow windows); `/works?filter=prefix:10.1145,isbn:<isbn>
  &rows=0` for the 14 ISBNs; `/works/10.1145/3287560.3287581`; monthly `prefix:10.1145` totals for 2019-01, 2022-06,
  2025-06 and 2026-06 (2,704; 3,776; 5,141; 4,389), to size the windows
- https://proceedings.mlr.press/v81/ and https://proceedings.mlr.press/ (2026-10-10)
- OpenAlex
- the pinned dblp release `dblp-2026-10-03.xml.gz`

## Milestone B as built: the official FAccT abstracts and the totals (2026-10-10)

The join is exact and one to one (`sources/facct_site.py`): 2022 and 2026 by exact title key, 2025 by DOI.

| Year | Join | Page entries | Records | Attached | Unmatched | Records without an abstract |
|---|---|---|---|---|---|---|
| 2022 | title | 181 | 181 | 169 | 12 | 12 |
| 2025 | DOI | 217 | 206 | 206 | 11 (the non-archival rows) | 0 |
| 2026 | title | 325 | 314 | 298 | 27 (11 non-archival, 16 worded differently) | 16 |

Totals as built: FAccT 1,230 records (1,239 ACM DOIs, minus 26 FAccT 2020 tutorial and CRAFT rows, plus 17 from PMLR
v81); AIES 2018–2023 575 records; AAAI 1980–2008 4,730 records in 23 held years. Crossref carries no section data, so
AIES 2018–2023's student abstracts and keynotes (141 entries of two pages or fewer, listed above) are in `main`, where
from 2024 OJS labels student abstracts `student_abstract`.
