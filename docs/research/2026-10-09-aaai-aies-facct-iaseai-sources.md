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
  facctconference.org pages (2026-10-10);
- the OpenAlex census behind `openalex_sources.toml` (auth, budget, DOI-route yield, the AAAI 1980–2008 source;
  2026-10-10).

Every count below was read live on 2026-10-09 (UTC; the late fetches, the 39173 retry and the dblp check are
2026-10-10, and say so).

## ojs.aaai.org (AAAI 2010–2026, AIES 2024–2025, IASEAI 2026)

- **Access.** robots.txt disallows only `/cache/` and sets no crawl delay. The server takes 2–3 s a page, and the
  harvest paces at least 3 s between requests. OAI-PMH runs at `/index.php/{AAAI,AIES,IASEAI}/oai`.
  - `Identify` gives earliest datestamp 2020-06-02 and `deletedRecord` persistent.
  - Formats: `oai_dc`, `marcxml`, `jats`, `rfc1807`, `oai_marc`. `ListRecords` pages hold 100 records, `ListIdentifiers` pages 500, and resumption tokens
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
  aaai.org's robots.txt (https://www.aaai.org/robots.txt, which redirects to https://aaai.org/robots.txt; re-read
  2026-10-16, TASK-236) sets `Crawl-delay: 43200` for `User-agent: *`. Milestone B takes AAAI 1980–2008 from the pinned dblp release:
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
  - AIES 2026 (Malmö, 12–14 Oct 2026) was not yet published on 2026-10-09; Vol. 9 (4 issues) appeared by
    2026-10-16: see §AIES 2026 below.
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
  `proceedings-article`s with a title, an author and a `page`. `op ingest crossref` gave each `count_ok: true`.
- **Entries of two pages or fewer (141), decided 2026-10-10 (TASK-224; the controller's ruling for the owner).** No
  official table of contents was reachable (the ACM DL blocks bots, Crossref has no sections), so page position
  is the only evidence. As built: the 18 front keynotes are `[[not_paper]]` rows of kind `keynote` (all below but
  .3375839 and .3462443, which look like papers and stay `main`); each year's student abstract block is a
  `[[section]]` page range, track `student_abstract` (2018 pp. 354–391: 19; 2019 pp. 521–560: 20; 2021 pp. 267–280:
  7; 2022 pp. 890–920: 31; 2023 pp. 939–1012: 31, the 19 short entries and the 12 student entries of 3–6 pages
  between them, since a range holds every work whose start page is in it and the taxonomy forbids page-count
  rules); the 25 short entries in the paper sequence stay `main`. AIES 2018–2023 is then 557 records: 449 `main`,
  108 `student_abstract`. The three kinds, as found:
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
  Student abstracts from 2024 on are OJS's `student` track (`STU`, `A25-SA`). The table gained a `[[section]]`
  table (venue, year, page range, track, label, check date, source) for the same track here (TASK-224).

### AIES 2026 (Vol. 9; census of 2026-10-16, TASK-217)

- `scripts/ojs_section_census.py AIES --refresh` on 2026-10-16: complete, 18 pages, `completeListSize` 716 = 715
  live + 1 deleted header; no unavailable article, no fallback set, nothing recovered by `GetRecord`, no
  duplicates. Vol. 7 (171) and Vol. 8 (279) are unchanged.
- Vol. 9: 265 live = `A26-1` Main Track I 67, `A26-2` Main Track II 60, `A26-3` Main Track III 57, `A26-4` Main
  Track IV 59 (243 `main`) + `A26-SA` Student Abstracts 22 (`student_abstract`); the one deleted header is in
  `A26-SA`. No front matter is listed. The issue pages (`issue/view/743`–`746`, the last "Main Track IV &
  Student Abstracts") show the same section titles, and issue 746 the same 59 and 22.
- No code changed: the year comes from the journal's offset (9 + 2017) and the tracks from the five new
  `[[section]]` rows, as the design expected (a new venue-year at an existing source needs a table row).

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
  recorded)*. The milestone C census of 2026-10-10 (§OpenAlex) reproduced 195 of 206 for 2025. For 2026 it
  found 290 abstracts among 314 works, the Crossref count, so the earlier 317 no longer stands. It found no
  truncated DOI, and found one duplicated DOI per roughly 250.
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
  records at the census (557 since TASK-224's 18 keynote rows). Every count equals the 2026-10-09 entry count, so no row needed a correction. The session's "1,341
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

Since TASK-225 and TASK-226 (2026-10-10) the not-paper rows are 33 (1990: 9, 1993: 2, 1996: 5, 1997: 3, 1998: 1,
2000: 2 added), so the total is **4,709 records**; §AAAI 1993–2008 sections below gives the tracks.

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

**For owner review** (left as papers by milestone B; decided 2026-10-10 by TASK-225 and TASK-226: the five
"(Abstract)" entries are invited talks on the official contents pages and are `[[not_paper]]` rows, `ArkinF97`
included, which the 1997 contents list under Invited Talks; `SelmanBDHMN96` and the eight 1990 statements are
`[[not_paper]]` rows of kind `panel`; the 1993–94 video and demonstration abstracts are track `demo` by the
contents' sections; `conf/aaai/1991w` stays excluded; `ChangN94`, which TASK-225 would have kept `main`, is in the
1994 Student Abstracts and is `student_abstract`, since the official contents win). The candidates as found:
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
1996 on name IAAI in their titles, but this release crossrefs no `conf/iaai/` paper to them (the design's §Sources 2: IAAI
has its own proceedings before 2010; `conf/iaai/` was not read here). The IAAI papers printed *in* the AAAI volumes
are keyed `conf/aaai/` and were read as AAAI `main`; since TASK-226 those of 1996–2008 are track `iaai` (§AAAI
1993–2008 sections).

**Other counts** (over the 4,758 inproceedings under keys dated 1980–2009):
- 678 author occurrences (326 distinct names) carry a dblp homonym number, which `clean_author` drops.
- No key fails `dblp.NATIVE`.
- No entry has a `publtype`.
- **No entry has a DOI `ee`**, so every AAAI 1980–2008 record has `urls.doi` empty. Milestone C's OpenAlex fill
  must match these records by title.
- No inproceedings dated 1980–2009 crossrefs a missing proceedings key.

## OpenAlex (milestone C census, 2026-10-10)

`scripts/openalex_census.py` reads OpenAlex only through `crawl.openalex_fetcher`: the host is api.openalex.org
only, it sends the repo's generic User-Agent, and it makes one request at a time, `openalex.MIN_INTERVAL` (1 s) apart.
It ran **keyless**: no `OPENALEX_API_KEY`, no `mailto` and no contact address of any kind. The DOI batches and listings
it fetched are the URLs `op ingest openalex` asks, so they sit in `<cache>/openalex/pages` for Task 15's crawl. The
candidates come from `crawl.replay_all` over the existing caches, offline. The census wrote nothing but the cache. It
ran 2026-10-10 21:09–21:16 UTC (387 s, of which about 290 s is the offline replay). Before it, a probe (7 requests,
21:06 UTC) read the API root, the two source searches and four per-year counts through the same fetcher.
**79 live requests in all**, with 26 cache hits in the census run.

**Endpoints and queries** (all `https://api.openalex.org`):
- `/` (the root, read live for its headers);
- `/sources?search=AAAI&per-page=50` and `/sources?search=National%20Conference%20on%20Artificial%20Intelligence&per-page=50`;
- `/sources?search=Fairness%2C%20Accountability%2C%20and%20Transparency&per-page=50`;
- `/works?filter=primary_location.source.id:<S…>&group_by=publication_year` for S4306420577, S4210191458,
  S4306400155 and S4306464630, plus S4210191458 with `publication_year:<2010`;
- `/works?filter=primary_location.source.id:S4363608463,publication_year:2025|2026[,has_abstract:true]&group_by=publication_year`;
- the DOI route: `/works?filter=doi:<d1>|…|<d50>&per-page=50&select=id,doi,title,publication_year,primary_location,abstract_inverted_index`
  (`openalex.doi_url`);
- the listing route: `/works?filter=primary_location.source.id:S4306420577,publication_year:<year>&per-page=200&select=…&cursor=*`
  (`openalex.listing_url`).

**Auth and budget.** A keyless request answers HTTP 200. Each answer carries `x-ratelimit-limit: 1000`,
`x-ratelimit-remaining`, `x-ratelimit-credits-used`, `x-ratelimit-cost-usd`, `x-ratelimit-limit-usd: 0.1`,
`x-ratelimit-remaining-usd`, `x-ratelimit-onetime-remaining: 0`, `x-ratelimit-prepaid-remaining-usd: 0` and
`x-ratelimit-reset` (seconds to the daily reset; 10,235 at 21:09 UTC, so midnight UTC).
- The keyless budget is **1,000 credits a day**, worth $0.10.
- A `/works` filter page or a `group_by` costs 1 credit ($0.0001). The API root also costs 1 credit.
- A `/sources?search=` costs 10 credits ($0.001).
- The census and probe used 106 credits, leaving 894.
- A full `op ingest openalex` is about 53 filter requests (30 DOI requests and 23 listing pages), about 5% of a
  keyless day, so no key is needed. Pages already cached cost nothing.
- A key, when there is one, goes as `Authorization: Bearer <key>` (`crawl.openalex_fetcher`), never in a URL. The
  answers' `access-control-allow-headers` list `Authorization`.

**Licence (read by the controller, 2026-10-10; each page re-read and its URL recorded 2026-10-16, TASK-236).** The
API itself states none: its root answer is `{"version", "documentation_url", "msg"}`, and a work answer carries only
each paper's own `license` field, which is not a data licence. The statements that matter are on three pages:
- OpenAlex's Pricing page, https://help.openalex.org/access/pricing/ (read 2026-10-16 through its Markdown sibling,
  https://help.openalex.org/access/pricing.md, which the help site's index names as each page's raw source; the
  rendered page was not compared): the data is released under "a CC0 public-domain license", with no
  personal-use carve-out and no permission needed.
- The work-object documentation, now https://help.openalex.org/data/works/attributes/ (the old
  https://help.openalex.org/api-entities/works/work-object redirects there; read 2026-10-16): OpenAlex does not ship
  abstracts as plain text, "for legal reasons", and gives the inverted index to rebuild them from.
- OpenAlex's terms page, https://openalex.org/terms (read 2026-10-16), names its PDFs as "the canonical versions".
  The terms of service, https://openalex.org/OpenAlex_termsofservice.pdf ("Last Revised: October 2, 2026"; sha256
  `58dacd4243971000748a2a1a232299328ef75c3723bd1df351ad7dbac5c89197`, read 2026-10-16), apply to the API and the
  snapshot by name. They grant a "freely revocable, limited license" to use the free features, and forbid
  republishing the Data without Impactstory's "prior written consent". **This contradicts the Pricing page's CC0
  statement.** No separate data-licence page was found: help.openalex.org's page index
  (https://help.openalex.org/llms.txt, read 2026-10-16) lists none, and its "Licenses" page
  (https://help.openalex.org/data/licenses/) covers the licences of the works OpenAlex indexes, not OpenAlex's own.
  The two conflict, and an owner decision is pending: since 2026-10-16 TASK-135 (the copyright-office consultation,
  a launch gate) covers it, and OpenAlex stays the decision-049 fallback, unchanged, until it is answered.

So the Pricing page calls the data CC0, though the terms of service (read 2026-10-16) restrict republication. Either
way the abstract text is deliberately not shipped: the `abstract_inverted_index` is the form OpenAlex releases, and
`openalex.rebuild` turns it back into text. The consequence for this project is that serving a rebuilt OpenAlex
abstract carries **the same copyright posture as serving a publisher's abstract**, not a CC0 one. It rests on
decision-018 (README §Abstracts on a public instance), the takedown list (a listed paper's abstract is withheld
whatever its source, so an OpenAlex abstract too) and the pending copyright-office consultation (TASK-135). The
`abstract_kind` label and filter let a review see and exclude these abstracts. The terms add a second, contractual
question that this posture doesn't answer: fair dealing (decision-018) is a copyright defence, not a licence to
breach a contract term. The terms were revised on 2026-10-02, before the 2026-10-10 crawl, so the extract was
taken under them, and serving rebuilt abstracts on a public instance is the kind of republication they cover. That
question is TASK-135's (item 1 of §Fixtures and what the census leaves for the owner).

### The DOI route (AIES 2018–2023, FAccT, two AAAI 2020 records)

The candidates are the AAAI, AIES and FAccT records with no abstract after every official source: **5,808** in all.
- 1,099 have a DOI:
  - AAAI 2020: 2;
  - AIES 2018–2023: 76, 89, 72, 113, 109, 98;
  - FAccT 2019–2024: 41, 69, 82, 12, 153, 167;
  - FAccT 2026: 16.
  - FAccT 2025 has none, because every 2025 record has its official abstract.
- 4,709 are DOI-less: AAAI 1980–2008, every held year.

The 1,099 DOIs make 22 batches of 50, and no DOI is unqueryable.
- **Halved batches.** Four batches matched 51 works, more than their 50-work page, because each held one duplicate.
  `harvest` halved each one, so the route made 30 requests and kept 26 lookups.
- **Every requested DOI has a work.** No DOI went unmatched (`doi_unmatched` 0).
- **No truncated or foreign DOI.** No work came back whose DOI was not requested (`doi_mismatch` 0).
- **Four DOIs returned twice:**
  - 10.1145/3306618.3314250 (AIES 2019; W2963086506, W2796639635);
  - 10.1145/3375627.3375862 (AIES 2020; W3005414547, W3101820912);
  - 10.1145/3442188.3445881 (FAccT 2021; W3101729298, W4288076238);
  - 10.1145/3442188.3445937 (FAccT 2021; W3134362900, W3122480037).
  - The simulated fill attaches two of them once, because their texts are identical. It refuses the other two
    (`doi_duplicate` 2): one AIES 2019 record and one FAccT 2021 record.
  - TASK-231 (owner ruling 2026-10-10): the AIES 2019 pair carries one abstract, word for word, but W2963086506's
    copy has PDF-extraction damage (lost fi/fl ligatures, hyphen splits), so a `[[duplicate_choice]]` row pins the
    clean W2796639635. The FAccT 2021 pair genuinely differs (a preprint and the published text) and stays refused.
    See §TASK-231 below.

**Yield** (simulated: `openalex.fill` over the census's lookups and the table below):

| Venue-year | Candidates (DOI) | Filled |
|---|---|---|
| AAAI 2020 | 2 | 2 |
| AIES 2018 / 2019 / 2020 / 2021 / 2022 / 2023 | 76 / 89 / 72 / 113 / 109 / 98 | 76 / 88 / 72 / 113 / 109 / 98 |
| FAccT 2019 / 2020 / 2021 / 2022 / 2023 / 2024 / 2026 | 41 / 69 / 82 / 12 / 153 / 167 / 16 | 41 / 69 / 81 / 12 / 153 / 167 / 16 |
| **Total** | **1,099** | **1,097** |

**FAccT 2025/2026 against the note's counts.** These close the *(unverified here)* marks of §FAccT. The census asked
OpenAlex for every FAccT 2025 and 2026 DOI the corpus holds, not only the candidates' DOIs.
- **2025:** 206 DOIs gave 206 works, and 195 have a usable abstract. This is the note's 195 of 206 exactly.
- **2026:** 314 DOIs gave 315 works. One DOI was returned twice: 10.1145/3805689.3806436 (W7152330660, W7166554585).
  290 DOIs have a usable abstract.
- OpenAlex's FAccT source, S4363608463 ("ACM Conference on Fairness, Accountability, and Transparency (FAccT)"),
  lists 206 works for 2025 (195 with an abstract) and 314 for 2026 (290 with an abstract).
- So the note's 293 of 317 is **not reproduced**. OpenAlex now lists 314 works for 2026, the Crossref count.
  The 3 extra works and 3 extra abstracts of the earlier reading are gone, most likely duplicates OpenAlex has
  since merged. The query behind the earlier figure was never recorded, so this can't be checked further.
- The session's "1,341 DOIs" is not explained by OpenAlex either. The DOI route shows one duplicate per roughly 250
  DOIs and no truncated DOI, nowhere near 102 extra.

### The listing route (AAAI 1980–2008)

`/sources?search=AAAI` gives 14 sources, and `/sources?search=National Conference on Artificial Intelligence` gives 1.
Two of them are the AAAI conference itself:
- S4306420577, "National Conference on Artificial Intelligence" (3,957 works, 1980–2021);
- S4210191458, "Proceedings of the AAAI Conference on Artificial Intelligence" (25,116 works, **none before 2010**).

The others are not the conference, so no row names them:
- symposia, workshops and other AAAI conferences (ICWSM, AIIDE, HCOMP, AIES);
- the repository S4306400155 (works from 2009 on);
- the ebook platforms S4306464630 "AAAI Press eBooks" (265 works over 1991–2015, books and symposia) and S4306464629.

**Why each row exists.** S4306420577 holds works in **every** held year from 1980 to 2008, so each of the 23 held
years has a `[[listing]]` row naming that source, with `works` = the census count. No year is left without a row.
The source also files 1, 9, 1 and 4 works under 1989, 1995, 2001 and 2003, years with no AAAI conference. Those get
no row, because the table refuses a not-held year.

**What the source mixes in.** It holds works for about 20–50% of each year's dblp records. The source also holds works
that match no record:
- the proceedings volumes themselves (for example "Proceedings of the Nineteenth National Conference on
  Artificial Intelligence");
- other venues' papers (ECAI-84, ICAPS 2004, and 2005–2008 weblog and symposium papers);
- OCR-garbled titles ("powek", "Found ations", "decomposab1lity").

Matching is one-to-one by exact title key, year and venue, so none of these can attach. A garbled title stays
`title_unmatched`, and is never widened to a fuzzy match.

| Year | Works (`works`) | With a usable abstract | DOI-less records | One-to-one title keys | Works matching no record | Filled (simulated) |
|---|---|---|---|---|---|---|
| 1980 | 49 | 36 | 95 | 46 | 3 | 34 |
| 1982 | 63 | 50 | 104 | 58 | 5 | 46 |
| 1983 | 55 | 50 | 92 | 51 | 4 | 47 |
| 1984 | 32 | 30 | 69 | 31 | 1 | 30 |
| 1986 | 94 | 55 | 188 | 72 | 22 | 50 |
| 1987 | 104 | 87 | 149 | 95 | 9 | 79 |
| 1988 | 95 | 68 | 150 | 80 | 15 | 59 |
| 1990 | 98 | 74 | 165 | 75 | 21 | 64 |
| 1991 | 82 | 65 | 144 | 72 | 10 | 59 |
| 1992 | 92 | 72 | 134 | 63 | 29 | 53 |
| 1993 | 60 | 41 | 133 | 52 | 8 | 38 |
| 1994 | 119 | 80 | 302 | 105 | 12 | 74 |
| 1996 | 115 | 75 | 300 | 98 | 17 | 71 |
| 1997 | 85 | 52 | 247 | 79 | 6 | 50 |
| 1998 | 55 | 49 | 205 | 38 | 17 | 36 |
| 1999 | 51 | 37 | 193 | 43 | 8 | 35 |
| 2000 | 52 | 40 | 231 | 42 | 10 | 35 |
| 2002 | 50 | 42 | 180 | 27 | 23 | 26 |
| 2004 | 80 | 44 | 194 | 29 | 51 | 25 |
| 2005 | 99 | 73 | 325 | 39 | 60 | 33 |
| 2006 | 138 | 96 | 385 | 51 | 87 | 41 |
| 2007 | 114 | 68 | 368 | 32 | 82 | 29 |
| 2008 | 120 | 99 | 356 | 53 | 67 | 47 |
| **Total** | **1,902** | **1,383** | **4,709** | **1,331** | | **1,061** |

**Listing-route refusals** (the simulated fill over all routes):
- `title_unmatched` 3,357, most of them records OpenAlex does not file under this source;
- `title_ambiguous` 21;
- `inverted_unreadable` 101;
- `inverted_gap` 50;
- `no_abstract` 119.
- All the `inverted_*` refusals are listing works, and every one is from 1980–2008. The DOI route had none.
  - Of the listing works whose index is `inverted_unreadable`, 117 have a key holding a CR or LF (`word\r\n`) or an
    empty key, which `rebuild` refused as no single word. TASK-231 changed the rule for the line breaks (§TASK-231
    below).
  - The 54 gaps split evenly: 27 are missing one position and 27 are missing more.
  - The rules stand, and nothing is forced.

**In all,** the fill would attach 2,158 of the 5,808 candidates: 1,097 by DOI and 1,061 by title. That leaves 3,650
records at `none`, 3,648 of them AAAI 1980–2008. With TASK-231's rulings the same extract attaches 2,248 (1,098 by
DOI, 1,150 by title) and leaves 3,560 at `none` (§TASK-231 below). These are the figures before `aaai_library` (§AAAI 1980–2008 abstracts, below): in the final build (2026-10-11) OpenAlex fills 1,117, 1,098 by DOI and 19 by title, because 4,536 AAAI 1980–2008 records already have AAAI's own abstract.

### Fixtures and what the census leaves for the owner

- **Fixtures.** `backend/tests/fixtures/http/openalex/doi-batch.json` (one FAccT 2023 batch of 50 DOIs) and
  `listing-1984.json` (the 32-work AAAI 1984 listing) are the census's own cache entries. They are scrubbed by
  `scrub.py`'s OpenAlex branch:
  - work ids, DOIs, years, the primary location and `meta` stay real;
  - titles become synthetic;
  - every inverted index is rebuilt from synthetic text of the same word count.
  - No abstract word is in the repository. The scrub makes every index dense, so the one `inverted_unreadable`
    index of the real 1984 page reads as a dense one in the fixture.
  - `test_openalex_recorded.py` pins them to the parser, the rebuild and the shipped table.
- **For the owner:**
  1. Open (2026-10-16): the Pricing page says CC0, but OpenAlex's terms of service (revised 2026-10-02) restrict
     republishing its data without written consent (§OpenAlex, Licence). The owner folded the question into TASK-135
     (2026-10-16), a launch gate; OpenAlex stays the fallback, unchanged, until it is answered. Abstracts rebuilt from
     the index are served on the publisher-abstract posture either way.
  2. Decided (TASK-231, 2026-10-10): a key holding CR/LF is read as its words joined by one space, at its one
     position (§TASK-231 below). The extract keeps the raw index, so no refetch was needed.
  3. Note that the `works` counts are a live total. If OpenAlex adds or merges a work under S4306420577 for a
     listed year, Task 15's crawl stops with `count_mismatch` and the row needs re-verifying. Nothing guesses.
  4. Note that 3,648 AAAI 1980–2008 records stayed `none` after the OpenAlex fill alone. OpenAlex files no more of them under an AAAI source; `aaai_library` (§AAAI 1980–2008 abstracts) then gave 4,536 of the 4,709 AAAI's own abstract.

### TASK-231: the owner's rulings on the fill's refusals (2026-10-10)

The owner reviewed the refusals of the real fill (snapshot 2026-10-10-22a339940466, extract 7fea58b98325) from a
read-only replay that reproduced the manifest's counts exactly.

**Line breaks inside a key.** OpenAlex tokenises on spaces only, so a paragraph break in the source stays inside one
key at one position (`word\r\n\r\nword`: 154 keys hold two CRLFs, 30 a single break, 3 a non-breaking space).
The evidence that this is one token, not two words: in every otherwise-dense index the key occupies exactly one
position, the next word is at the next position, and nothing is missing there. 157 of the 184 break keys end their
first part in sentence punctuation.
- **Ruling:** `openalex.rebuild` reads such a key as its words joined by one space, at its one position (each
  whitespace run becomes one space, and none is kept at the key's edges; 5 keys start with `\r\n`). An empty or
  whitespace-only key is still `inverted_unreadable`, and the gap and conflict rules still apply. It is deterministic
  and exact: nothing is moved or matched loosely. The paragraph break itself is lost, as it is for every abstract
  `common.clean_abstract` reads.
- **Not checked:** none of the 101 records has an official abstract to compare against. The only evidence of
  fidelity is internal (dense positions, breaks at sentence boundaries).

**The AIES 2019 duplicate.** 10.1145/3306618.3314250 ("Incomplete Contracting and AI Alignment") is answered by
W2796639635 and W2963086506. They hold the same abstract word for word, but W2963086506 has PDF-extraction damage
(`nding`, `rst`, `par- allels`). **Ruling:** a cited `[[duplicate_choice]]` row in `openalex_sources.toml` pins
W2796639635. The fill attaches it (counted `attached_doi` and `duplicate_chosen`), and the build stops
(`duplicate_choice_unmatched`) if a later extract answers the DOI without that work among two or more works. No text
heuristic (de-hyphenation, ligature repair) is applied: the choice is one checked row, not a rule.

**Kept refused:** FAccT 2021's 10.1145/3442188.3445881 (the two texts genuinely differ); all 21 `title_ambiguous`,
Shvaytser 1990 included; `inverted_gap`, `no_abstract` and `title_unmatched`.

**Predicted effect** (an offline replay of the extract over the snapshot's records with the OpenAlex claims removed;
the snapshot itself is rebuilt later):

| | Before | With the rulings |
|---|---|---|
| Attached by DOI | 1,097 | 1,098 (1 `duplicate_chosen`) |
| Attached by title | 1,061 | 1,150 |
| `inverted_unreadable` | 101 | 2 (empty-string keys) |
| `inverted_gap` | 50 | 60 (10 formerly unreadable indexes have a hole) |
| `doi_duplicate` | 2 | 1 |
| `title_ambiguous` / `no_abstract` / `title_unmatched` | 21 / 119 / 3,357 | unchanged |

### Does an inline provenance label let a reviewer judge and filter fallback text? (gate C round 1)

The design assumes that a reviewer who sees "Abstract via OpenAlex" on a hit or a paper page, or the Abstract
source facet, understands that the text is a third party's and chooses `abstract_kind:official` when that matters.
Verdict: **no evidence found.** No verified study shows that provenance labels change expert screening behaviour. The
nearest work, on trust calibration among web searchers, transfers weakly to protocol-driven Boolean search by
systematic reviewers. The label is kept because it is honest and costs nothing, not because it is known to work. A
small think-aloud with systematic reviewers on the paper and coverage pages is TASK-233, for `usability-tester`
(`Ethics: not submitted`, TASK-233). The rest of this note's evidence is a source census and needs no HCI
literature.

## Licence posture

What each source states about reuse, and what the index does with its text. None of this is legal advice; the
project's position is decision-018 (README §Abstracts on a public instance).

| Source | Stated licence | Checked |
|---|---|---|
| ojs.aaai.org (AAAI, AIES, IASEAI) | `dc:rights` "Copyright (c) <year> …"; no open licence | 2026-10-09, in every record read |
| ACM DL (FAccT 2019–2026, AIES 2018–2023) | none found for metadata or abstracts (the DL answers 403; ACM is open access since 2026-01-01, which covers the papers, not a metadata licence) | 2026-10-09 |
| facctconference.org CSVs and the 2022 page | none found. Milestone B stores and shows their abstracts (2022, 2025, 2026) | 2026-10-09 *(page not recorded; unverified here)*; 2026-10-10: not re-read (the review had no network) |
| Crossref (FAccT 2019–2026, AIES 2018–2023) | not read: milestone B takes titles, authors and DOIs from it and no abstract (it holds none for these DOIs) | not checked (2026-10-10, no network in the review) |
| PMLR v81 (FAccT 2018) | PMLR's CC BY 4.0, as README states for its volumes (known from ICML 2017, v70); v81's own page not read for it | 2026-10-10 *(v81 unverified)* |
| the pinned dblp release | CC0, as spec 01 records for the Dagstuhl DROPS release (titles, no abstracts; decision-047, and AAAI 1980–2008 in milestone B) | spec 01's record of the release page; not re-read 2026-10-10 |
| OpenAlex (milestone C fallback) | the Pricing page (https://help.openalex.org/access/pricing/) says "a CC0 public-domain license"; the terms of service (https://openalex.org/OpenAlex_termsofservice.pdf, revised 2026-10-02) grant a "freely revocable, limited license" and forbid republishing the Data without "prior written consent", which contradicts it (§OpenAlex, Licence); abstracts are not shipped as text "for legal reasons" and are rebuilt from the inverted index (https://help.openalex.org/data/works/attributes/). A rebuilt abstract is served on the publisher-abstract posture: decision-018, the takedown list and TASK-135 | 2026-10-10: controller read both help pages; 2026-10-16: all three pages re-read, URLs recorded (TASK-236) |

**Index versus fixtures.** The live index stores and shows an OJS abstract with its attribution ("AAAI Digital
Library") and a link to the paper's own page on ojs.aaai.org, never the full text, on decision-018's fair-dealing
basis, as for the other non-CC sources. Since milestone B it does the same for the official FAccT abstracts of 2022,
2025 and 2026: each is shown with its attribution ("FAccT conference site") and a link to the paper's DOI, on the
same basis, since no licence for them was found. Committed test fixtures are different: their titles, authors and abstracts
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
plain GETs of the pages named; dblp.org never fetched). Six more followed on 2026-10-10 (below, "AAAI list counts"),
and every other new-venue main cell this table classifies as not gated carries a cited note (TASK-222). Classes: **gateable** (an official statement whose
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
| AAAI 2010 | 262 | counted on AAAI's own list: 202 main technical (short papers included) + 60 in five special tracks; Nectar and senior member excluded | https://web.archive.org/web/20100830185521/http://www.aaai.org/Conferences/AAAI/2010/aaai10papers.php | 262 | gateable (row, list count, 2026-10-10) |
| AAAI 2011 | 240 | counted on AAAI's own list, which has no Robotics Program | https://web.archive.org/web/20120605015434/http://www.aaai.org/Conferences/AAAI/2011/aaai11accepts.php | 248 | definition mismatch (note) |
| AAAI 2012 | 292 | counted on AAAI's own list: 220 main technical (poster-only full papers included) + 26 + 11 + 21 + 14 in four special tracks | https://aaai.org/wp-content/uploads/2023/01/aaai12accepted-papers.pdf | 294 | gateable (row, list count, 2026-10-10) |
| AAAI 2014 | 398 | counted on AAAI's own list: the 22 AAAI technical categories (submissions 1,406) | https://web.archive.org/web/20150906033202/http://www.aaai.org/Conferences/AAAI/2014/aaai14accepts.php | 398 | gateable (row, list count, 2026-10-10) |
| AAAI 2016 | 548 | AAAI's list, "ordered … in each proceedings category", matching the OJS sections exactly (submissions 2,132) | aaai.org list; issue page 303 | 548 | not gated: the list appears derived from the proceedings (note) |
| AAAI 2017 | 637 | counted on AAAI's own list: 599 main technical + 38 in three special tracks (submissions 2,571) | https://aaai.org/wp-content/uploads/2023/01/aaai17accepted-papers.pdf | 639 | gateable (row, list count, 2026-10-10) |
| AAAI 2020 | 1,614 | counted on AAAI's own pre-camera-ready lists: 1,589 main technical + 25 AI for Social Impact | https://aaai.org/wp-content/uploads/2023/01/AAAI-20-Accepted-Paper-List.pdf and https://aaai.org/wp-content/uploads/2023/01/AAAI-20-Accepted-AISI-Papers.pdf | 1,610 | gateable (row, list count, 2026-10-10) |
| AAAI 2021 | 1,697 | counted on AAAI's own list as archived 2020-12-30, before the conference: 1,657 main technical + 40 AI for Social Impact, both from the one PDF (the 40 its last section, pp. 121–124); the later copy has 1,656 + the same 40 | https://web.archive.org/web/20201230042125id_/https://aaai.org/Conferences/AAAI-21/wp-content/uploads/2020/12/AAAI-21_Accepted-Paper-List.Main_.Technical.Track_.pdf; later copy https://aaai.org/wp-content/uploads/2023/01/AAAI-21_Accepted-Paper-List.Main_.Technical.Track_.pdf | 1,694 | gateable (row, list count, 2026-10-10; re-checked and re-counted from the pre-conference copy 2026-10-16, owner's choice) |
| AAAI 2022–2026 | none | chairs' notification emails quoted on third-party sites and aggregator figures only (1,349; 1,721; 2,342; 3,032; 4,167), apparently the main technical track alone | none official | see the per-year table | not found (note) |
| IASEAI 2026 | 92 | accepted research papers, 35 of them non-archival and unpublished on OJS | https://ojs.aaai.org/index.php/IASEAI/issue/view/741 | 57 | definition mismatch: recorded, not gated |

- **AIES.** The chairs' statements are not the OJS issue listing (whose totals this note once called circular);
  the 2025 program is on the conference's own site. Whether "accepted" is before or after withdrawals is not
  stated; the exact match with the listing suggests none.
- **AAAI 2018, 2019.** "Original research publications" is read as the technical program, special tracks
  included; the front matter does not itemise.
- **AAAI list counts (2026-10-10; one independence rule since gate C round 1, 2026-10-11).** For 2010, 2012, 2014,
  2016, 2017, 2020 and 2021 no AAAI document *states* an accepted count (prefaces, conference pages and press releases
  give submissions only), so the rows count the entries of AAAI's own accepted-paper list (aaai.org PDFs, or aaai.org
  pages archived by the Wayback Machine). Each row's description says "counted" and names the list, and its
  definition must equal our `main` cell within 1%. The review found the independence test applied unevenly: 2016 was
  refused because its list matched the proceedings exactly, while 2010 and 2014 matched exactly too, and 2014's only
  copy was captured a year after publication. The controller's rulings (gate C rounds 1 and 2) are one rule: A list counts as independent of the proceedings when it states that it is pre-camera-ready, visibly differs from the proceedings in content (a different count or membership), or survives in a dated copy archived before the proceedings (the owner, 2026-10-16, TASK-234); each shows it was not derived from them. Per row:
  - 2010 (262 = 262), 2014 (398 = 398) and 2016: each matches the proceedings exactly, and nothing on it says it was
    made before them (2010's and 2014's only archived copies were captured on 2010-08-30 and 2015-09-06, after
    publication). Each is an ungated cell with a note.
  - 2012, 2017, 2020 and 2021: the PDFs sit under `wp-content/uploads/2023/01/`, the date of AAAI's site migration,
    not of the lists, so their upload dates say nothing. All four are gated, each row naming its ground: the 2020
    lists say they were made before camera-ready; 2012 and 2017 differ from the proceedings the crawl reads in count
    (deltas +2 and +2 on the snapshot below; 2020's is −4); and 2021's is counted from a copy archived before the
    conference (next bullet; Δ −3).
  - 2021 (re-checked 2026-10-16, TASK-234): the 40 AI for Social Impact papers are in the list PDF itself. Its
    first page says the special track's list "appears at the end of this document", and its last section,
    "Special Track on AI for Social Impact" (pp. 121–124), has 40 numbered entries; the 1,656 main technical are
    the entries before it in the copy aaai.org serves now (counted 2026-10-16 by the AI assistant session working
    for the owner, from the 2023-09-29 capture
    `https://web.archive.org/web/20230929155523id_/https://aaai.org/wp-content/uploads/2023/01/AAAI-21_Accepted-Paper-List.Main_.Technical.Track_.pdf`).
    No separate AI for Social Impact list was found under either path the Internet Archive holds:
    `https://web.archive.org/cdx/search/cdx?url=aaai.org/Conferences/AAAI-21/*&collapse=urlkey` lists 887 URLs, none
    another accepted list, and `https://web.archive.org/cdx/search/cdx?url=aaai.org/wp-content/uploads/2023/01/AAAI-21*&collapse=urlkey`
    lists four files, this PDF, the program committee, the schedule overview and the poster schedule (both queried
    2026-10-16; AAAI-20's separate AISI list sits under the 2023/01 path, AAAI-21's doesn't). The PDF doesn't say it
    predates the proceedings, and the later copy (SHA-1 base32 `SOFX7UV3F7DWXILKLOLHRV5OKIO76JPZ`, embedded creation
    date 2021-01-29) was first captured on 2021-11-10, at the old path
    `aaai.org/Conferences/AAAI-21/wp-content/uploads/2020/12/AAAI-21_Accepted-Paper-List.Main_.Technical.Track_.pdf`.
    An earlier copy at that path, captured on 2020-12-30 and 2021-01-26 (`DZJNTKYZTPBVFWBS5AXMQIUBXI457YSX`,
    embedded creation date 2020-12-23), was made before the conference (2021-02-02 to 02-09) and so before the
    proceedings. Its entries were counted 2026-10-16 by the AI assistant session working for the owner, from
    `https://web.archive.org/web/20201230042125id_/https://aaai.org/Conferences/AAAI-21/wp-content/uploads/2020/12/AAAI-21_Accepted-Paper-List.Main_.Technical.Track_.pdf`
    (the downloaded file's SHA-1 matches the CDX digest `DZJN…`). It lists the same 40 AI for Social Impact papers and 1,657 main technical: paper 7140 ("Fused
    Sequential and Hierarchical Representation Model for Aspect Term Extraction") is on it and not on the later copy,
    and is not in the index (snapshot `2026-10-11-93c2937e2f29`), so the later copy was edited toward the
    proceedings. **The owner chose the earlier copy (2026-10-16)**, since official counts come from a list made
    before the proceedings: the row counts it, 1,697 (Δ −3, 0.18% on snapshot `2026-10-11-93c2937e2f29`; the gate
    passes), and names the later copy (1,696) too.

  The deltas are those of snapshot `2026-10-10-9efa49481112` and are unchanged on the final snapshot
  `2026-10-11-93c2937e2f29` (`docs/results/2026-10-11-coverage.md`), where the gate passes at 81 of 82 cells; with
  2021 re-counted at 1,697 its delta is −3 (`docs/results/2026-10-16-coverage.md`), and the gate still passes.
- **Ungated-cell notes (TASK-222).** AAAI 2010, 2011, 2014, 2016 and 2022–2026 main and IASEAI 2026 main each carry a
  cited note
  saying why they are not gated (`official_counts.UNGATED_NOTES`, `coverage-sources.md` §Ungated cells with a note),
  served on `/coverage` and listed in the coverage report.
- **AAAI 2020–2026.** The trackers' figures sit close to our `main` minus the special tracks and Journal Track, so
  they likely count the Main Technical Track only; even an official figure of that kind would be a definition
  mismatch with our `main`. For 2020 and 2021 AAAI's own accepted-paper lists itemise the special tracks and back a
  row (above); for 2022–2026 no such list was found.
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
- api.openalex.org (2026-10-10, keyless; §OpenAlex lists every query)
- https://www.aaai.org/robots.txt, which redirects to https://aaai.org/robots.txt (`Crawl-delay: 43200`; read
  during this research in 2026-10 and re-read 2026-10-16, TASK-236), and web.archive.org's CDX index and `id_`
  captures of `www.aaai.org/Library/` (2026-10-10, TASK-232)
- OpenAlex's Pricing page, https://help.openalex.org/access/pricing/, and its work-object documentation, now
  https://help.openalex.org/data/works/attributes/ (both read by the controller 2026-10-10, re-read 2026-10-16);
  its terms page, https://openalex.org/terms, and terms of service, https://openalex.org/OpenAlex_termsofservice.pdf
  (2026-10-16); help.openalex.org's page index, https://help.openalex.org/llms.txt (2026-10-16), for a data-licence
  page (none)
- AAAI-21's accepted-paper list, https://aaai.org/wp-content/uploads/2023/01/AAAI-21_Accepted-Paper-List.Main_.Technical.Track_.pdf,
  and its earlier copies under `aaai.org/Conferences/AAAI-21/wp-content/uploads/2020/12/` in the Internet Archive
  (CDX and `id_` captures of 2020-12-30 and 2023-09-29; read 2026-10-16, TASK-234)
- the pinned dblp release `dblp-2026-10-03.xml.gz`

## AAAI 1993–2008 sections (TASK-224/225/226, decision-050, 2026-10-10)

TASK-225's evidence found 767 AAAI main-track entries of 1993–2008 of two pages or fewer, mostly in trailing
blocks. The official source for their sections is the AAAI Digital Library contents page
`http://www.aaai.org/Library/AAAI/aaai<yy>contents.php` (the live site no longer serves it), read from Wayback
captures of 2013-01-17/18, which give each section heading and each paper's start page; the IAAI contents pages
`.../Library/IAAI/iaai<yy>contents.php` give the IAAI papers that 1996–2000, 2004 and 2005 print in the AAAI volumes
(captures of 2012-06-05, 2013-01-18 and, for 2000, 2013-10-04). Every capture is in the table below; each
`[[section]]` row of `dblp_aaai.toml` cites its own in `source`. Every dblp entry was joined to the contents by start
page and title (all but Sultanik05, Thornton05 and WangL05 matched), and each section became a `[[section]]` row: a
page range from the lowest dblp start page to the highest dblp end page of the entries the contents list in it.

| Page | Capture | Captured | Evidences |
|---|---|---|---|
| 1993 AAAI contents | https://web.archive.org/web/20130118005519/http://www.aaai.org/Library/AAAI/aaai93contents.php | 2013-01-18 | the year's sections and start pages (135 entries; dblp's main keys hold 135) |
| 1994 AAAI contents | https://web.archive.org/web/20130118002450/http://www.aaai.org/Library/AAAI/aaai94contents.php | 2013-01-18 | the year's sections and start pages (302 entries; dblp's main keys hold 302) |
| 1996 AAAI contents | https://web.archive.org/web/20130118002805/http://www.aaai.org/Library/AAAI/aaai96contents.php | 2013-01-18 | the year's sections and start pages (269 entries; dblp's main keys hold 289) |
| 1997 AAAI contents | https://web.archive.org/web/20130118001218/http://www.aaai.org/Library/AAAI/aaai97contents.php | 2013-01-18 | the year's sections and start pages (181 entries; dblp's main keys hold 213) |
| 1998 AAAI contents | https://web.archive.org/web/20130118000422/http://www.aaai.org/Library/AAAI/aaai98contents.php | 2013-01-18 | the year's sections and start pages (184 entries; dblp's main keys hold 206) |
| 1999 AAAI contents | https://web.archive.org/web/20130118002324/http://www.aaai.org/Library/AAAI/aaai99contents.php | 2013-01-18 | the year's sections and start pages (176 entries; dblp's main keys hold 193) |
| 2000 AAAI contents | https://web.archive.org/web/20130118002858/http://www.aaai.org/Library/AAAI/aaai00contents.php | 2013-01-18 | the year's sections and start pages (215 entries; dblp's main keys hold 233) |
| 2002 AAAI contents | https://web.archive.org/web/20130118002719/http://www.aaai.org/Library/AAAI/aaai02contents.php | 2013-01-18 | the year's sections and start pages (181 entries; dblp's main keys hold 180) |
| 2004 AAAI contents | https://web.archive.org/web/20130118001614/http://www.aaai.org/Library/AAAI/aaai04contents.php | 2013-01-18 | the year's sections and start pages (171 entries; dblp's main keys hold 194) |
| 2005 AAAI contents | https://web.archive.org/web/20130118001834/http://www.aaai.org/Library/AAAI/aaai05contents.php | 2013-01-18 | the year's sections and start pages (268 entries; dblp's main keys hold 325) |
| 2006 AAAI contents | https://web.archive.org/web/20130117070935/http://www.aaai.org/Library/AAAI/aaai06contents.php | 2013-01-17 | the year's sections and start pages (368 entries; dblp's main keys hold 385) |
| 2007 AAAI contents | https://web.archive.org/web/20130117223503/http://www.aaai.org/Library/AAAI/aaai07contents.php | 2013-01-17 | the year's sections and start pages (369 entries; dblp's main keys hold 368) |
| 2008 AAAI contents | https://web.archive.org/web/20130118002504/http://www.aaai.org/Library/AAAI/aaai08contents.php | 2013-01-18 | the year's sections and start pages (357 entries; dblp's main keys hold 356) |
| 1996 IAAI contents | https://web.archive.org/web/20120605045614/http://www.aaai.org/Library/IAAI/iaai96contents.php | 2012-06-05 | the IAAI papers printed in the AAAI volume (18 entries) |
| 1997 IAAI contents | https://web.archive.org/web/20120605040048/http://www.aaai.org/Library/IAAI/iaai97contents.php | 2012-06-05 | the IAAI papers printed in the AAAI volume (32 entries) |
| 1998 IAAI contents | https://web.archive.org/web/20120605045432/http://www.aaai.org/Library/IAAI/iaai98contents.php | 2012-06-05 | the IAAI papers printed in the AAAI volume (22 entries) |
| 1999 IAAI contents | https://web.archive.org/web/20120605045227/http://www.aaai.org/Library/IAAI/iaai99contents.php | 2012-06-05 | the IAAI papers printed in the AAAI volume (17 entries) |
| 2000 IAAI contents | https://web.archive.org/web/20131004120945/http://www.aaai.org/Library/IAAI/iaai00contents.php | 2013-10-04 | the IAAI papers printed in the AAAI volume (17 entries) |
| 2004 IAAI contents | https://web.archive.org/web/20130118001753/http://www.aaai.org/Library/IAAI/iaai04contents.php | 2013-01-18 | the IAAI papers printed in the AAAI volume (24 entries) |
| 2005 IAAI contents | https://web.archive.org/web/20130118002518/http://www.aaai.org/Library/IAAI/iaai05contents.php | 2013-01-18 | the IAAI papers printed in the AAAI volume (18 entries) |
| 2005 demo paper pages | https://web.archive.org/web/20130312180408/http://www.aaai.org/Library/AAAI/2005/isd05-002.php (isd05-001 … 018 captured 2013-03-12; 019 … 022 on 2006-10-05, e.g. https://web.archive.org/web/20061005161718/http://www.aaai.org/Library/AAAI/2005/isd05-020.php) | 2013-03-12, 2006-10-05 | the page numbers of the 22 Intelligent Systems Demonstrations, pp. 1670–1713 |
| 2005 robot paper pages | https://web.archive.org/web/20130312181902/http://www.aaai.org/Library/AAAI/2005/rbc05-001.php (rbc05-001 … 015) | 2013-03-12 | the page numbers of the 15 Mobile Robot Competition and Exhibition entries, pp. 1716–1744 |

| Section (variants) | Track | Years | Records |
|---|---|---|---|
| Student Abstracts | `student_abstract` | 1994, 1996–2000, 2002, 2004–2008 | 399 |
| (SIGART/AAAI) Doctoral Consortium | `consortium` | 1996–2000, 2002, 2004–2008 | 158 |
| Video Abstracts (1993), Video Program (1994), Intelligent Systems Demonstrations | `demo` | 1993, 1994, 1999, 2000, 2002, 2004–2008 | 127 |
| IAAI Case Studies (1996), Deployed and Emerging Applications | `iaai` | 1996–2000, 2002, 2004–2008 | 232 |
| (Mobile) Robot Competition and Exhibition (Abstracts) | `other` | 1996, 1997, 1999, 2000, 2005–2007 | 64 |
| NECTAR Papers, Senior Member Papers | `other` | 2006–2008 | 91 |
| AAAI Member Abstracts (no pages in dblp: 18 `[[track]]` rows) | `other` | 2006 | 18 |
| Invited Talks, two pages or fewer | `[[not_paper]]`, kind `invited talk` | 1993, 1996–1998, 2000 | 12 removed |

Rulings (2026-10-10, the controller for the owner): robot competition and exhibition entries are `other` (event
reports, not system demos, as the 2010+ SPOT section); NECTAR and Senior Member Papers are `other`, as the owner
decided for the same sections from 2010 (TASK-218, `ojs_sections.toml`); invited entries of more than two pages stay
`main` as full papers (e.g. Kambhampati96a, Hinton00, Epstein99, Geffner02, DomingosKPRS06, Walsh07); the 2008 Short
Papers section is a technical-program section and stays `main` (11), as does GaurJH97 (a full paper dblp gives only a
start page). Invited-talk sections have no range (their short talks are rows; the 1997 contents print ArkinF97 at
p. 748, dblp at 755). 2006 Student Abstracts starts at 1853 (AhmadiS06a's page; dblp's pages field is `1853-`).

- **2005's demonstrations and robot entries.** `aaai05contents.php` lists both sections, "Intelligent Systems
  Demonstrations" (all 22 `isd05-` entries) and "Mobile Robot Competition and Exhibition" (all 15 `rbc05-`
  entries), but prints no page numbers for them. The ranges (pp. 1670–1713 and 1716–1744) come from the entries' own
  aaai.org paper pages, whose pages are contiguous; the section itself is the contents page's.
- **dblp page oddities.** `BlackH06`'s pages `855-1856` (for 1855–1856) put it outside its range, so a `[[track]]` row
  gives it `student_abstract`. `LimCKO00` (`1020-1015`) and `HanF08` (`1802-1893`) start inside their ranges and
  need no row; `AhmadiS06a` (`1853-`) reads as start page 1853. 2006's 18 AAAI Member Abstracts have no pages field
  at all, so each has a `[[track]]` row (`other`); a main-key entry of a year with sections that has no readable start
  page and no row now stops the replay (`unplaced_page`), so the next one can't fall to `main` unseen.
- **Entries the contents print without a page, or under another title, which the ranges hold:** `BraunlKLM96`
  (p. 1351, robot abstracts), `Taylor96` (p. 1411, student abstracts), `BarishKCMPS00` (pp. 980–987, the first IAAI
  2000 Emerging Applications entry, printed without a page number); `Murphy96` is listed under a shorter title;
  `Hoz-WeissKWS02` is listed with a misprinted page (1174). The ranges also move six entries of three pages or more
  that the contents list in the same sections (`NumaoTN02a`, `ZhouH02`, `TaylorS06`, `ValenteJV06`, `Wang06`,
  `HanF08`).
- **Unresolved.** `Sultanik05` (pp. 1628–1629) and `Thornton05` (pp. 1630–1631) sit between the last listed
  student abstract and the Doctoral Consortium but are on no aaai.org page (Wayback holds `sa05-001`…`022` only); so
  is `WangL05` (pp. 1632–1635), four pages, in the same gap. They stay `main`: counted as technical-program papers
  for want of evidence, not on evidence.
- **IAAI 1996–1999.** The AAAI contents pages of these years leave out the IAAI papers printed in the volume (blocks
  of 18, 32, 22 and 17 entries no AAAI heading lists). The IAAI contents pages list exactly those entries: every
  dblp entry in each range matched an IAAI entry by start page and title (title ratio ≥ 0.8 for all), and each IAAI
  entry matched one dblp entry. The one page difference: 1997's `DevA97` starts at p. 853 in dblp, p. 852 on the
  IAAI page (same title); the range starts at dblp's 853. Ranges: 1996 pp. 1421–1587 (Case Studies), 1997
  pp. 853–1085, 1998 pp. 1013–1166, 1999 pp. 778–896. Every IAAI year of 1996–2008 is resolved.

**Result** (the replay test `backend/tests/unit/ingest/test_track_rules_replay.py` pins these counts over the
pinned release): of the 4,689 main-volume entries, 33 are not-paper rows and 1,089 take a section's track, so AAAI
1980–2008 is 4,709 records (4,730 before): 3,567 `main`, 399 `student_abstract`, 158 `consortium`, 127 `demo`, 232
`iaai`, 173 `other`, 53 `workshop`. AIES 2018–2023's 108 `student_abstract` records are all inferred from page
position; no official contents page confirms any of them. Per year (AAAI):

| Year | student_abstract | consortium | demo | iaai | other | not-paper rows added |
|---|---|---|---|---|---|---|
| 1990 | | | | | | 8 |
| 1993 | | | 7 | | | 2 |
| 1994 | 77 | | 6 | | | |
| 1996 | 43 | 15 | | 18 | 9 | 5 |
| 1997 | 30 | 13 | | 32 | 16 | 3 |
| 1998 | 24 | 16 | | 22 | | 1 |
| 1999 | 29 | 16 | 17 | 17 | 4 | |
| 2000 | 38 | 12 | 12 | 18 | 2 | 2 |
| 2002 | 17 | 13 | 10 | 18 | | |
| 2004 | 17 | 12 | 21 | 24 | | |
| 2005 | 22 | 16 | 22 | 18 | 15 | |
| 2006 | 25 | 13 | 13 | 21 | 77 | |
| 2007 | 42 | 17 | 9 | 22 | 26 | |
| 2008 | 35 | 15 | 10 | 22 | 24 | |

## Milestone B as built: the official FAccT abstracts and the totals (2026-10-10)

The join is exact and one to one (`sources/facct_site.py`): 2022 and 2026 by exact title key, 2025 by DOI.

| Year | Join | Page entries | Records | Attached | Unmatched | Records without an abstract |
|---|---|---|---|---|---|---|
| 2022 | title | 181 | 181 | 169 | 12 | 12 |
| 2025 | DOI | 217 | 206 | 206 | 11 (the non-archival rows) | 0 |
| 2026 | title | 325 | 314 | 298 | 27 (11 non-archival, 16 worded differently) | 16 |

Totals as built: FAccT 1,230 records (1,239 ACM DOIs, minus 26 FAccT 2020 tutorial and CRAFT rows, plus 17 from PMLR
v81); AIES 2018–2023 575 records; AAAI 1980–2008 4,730 records in 23 held years. Since TASK-224/225/226: AIES
2018–2023 557 records (449 `main`, 108 `student_abstract`), AAAI 1980–2008 4,709 records (3,567 `main`; §AAAI
1993–2008 sections).

## AAAI 1980–2008 abstracts: the archived aaai.org paper pages (TASK-232, decision-051, 2026-10-10)

Before this source, after the OpenAlex fill alone, 3,648 of the 4,709 AAAI 1980–2008 records had no abstract and the other 1,061 had
OpenAlex's. dblp gives these years none, but each record's dblp `ee` is its old aaai.org paper page,
`www.aaai.org/Library/{AAAI,IAAI}/<yyyy>/<id>.php`, which printed the abstract.

**The crawl-delay decision.** aaai.org's robots.txt (https://www.aaai.org/robots.txt; see §ojs.aaai.org) sets
`Crawl-delay: 43200` (one request every 12 hours: about 6.3 years for 4,609 pages), and its 2023 site dropped the
Library pages. The Crawl-delay is a request to crawlers of aaai.org. Reading the Internet Archive's copies does not
breach it, since aaai.org is never fetched, but it does signal that AAAI does not want its site crawled, and the
record should say so. Asking AAAI for the abstracts, or for permission, is not recorded among the options the decision
weighed; it stays open, through the channel the copyright-office consultation (TASK-135) uses. The owner approved reading the Internet
Archive's captures instead (decision-051): the only host is `web.archive.org`, for the captures and its CDX index;
aaai.org is never fetched, so the crawl delay is never in play and aaai.org bears no load. The archive is read one
request at a time, at least 3 s apart, with the repo's generic User-Agent and no contact string. The text is AAAI's
copyright, served on the same posture as the ojs.aaai.org abstracts (decision-018, the takedown list, TASK-135).

**What the research showed** (kept outside git with the milestone's task reports, so not re-checkable from the
repository; the sample is listed here instead): 15 of 15 sampled captures held the abstract, and the 4 that could be
checked against the live new-site abstract were identical to it. The sample is one record per year for 15 years
spread over 1980–2008 (the years chosen by hand to span the range), each year's record drawn at random (`random.seed(232)`) from that year's records with no abstract and an
aaai.org `ee`: Faugeras80, EtheringtonR83, KilhofferK86, Brodie88, CaferraDH91, FrazierP93, WeldE94, Haynes96,
DetermanB98 (IAAI), LiberatoreS00, FangKLS02, TuanBZS04, ConitzerS06, KimuraSN07 and KuchibatlaM08 (dblp keys
`conf/aaai/<key>`). Fifteen of fifteen only puts a 95% one-sided lower bound near 82% on the share of pages that hold
an abstract, so the sample shows the source exists, not how complete it is: the evidence for that is the full
harvest's refusal counts, which "As built" records after the harvest. `https://web.archive.org/web/<timestamp>id_/<url>` returns the archived bytes exactly, and their SHA-1 (base32)
is the CDX digest. The old layout is `<div id="abstract"><h1><a href=…pdf>TITLE</a></h1><p class="left"><i>AUTHORS</i>
</p><p>ABSTRACT</p>`; the 2007-style pages break lines inside the abstract and add `Subjects:` / `Submitted:`
paragraphs. One placeholder was found, `None - 2 page paper is an abstract` (aaai06-329).

**The census** (`scripts/aaai_library_census.py`, 2026-10-10; two CDX requests, nothing else fetched). It read the
4,709 AAAI 1980–2008 dblp records of snapshot `2026-10-10-22a339940466` and their `ee` links from the pinned dblp
extract (both offline), then every status-200 capture under `www.aaai.org/Library/AAAI/` (31,206) and `…/IAAI/`
(3,275): 7,795 distinct pages, none set aside (no query, port, non-HTML type or missing digest).

| | Records |
|---|---|
| AAAI 1980–2008 dblp records | 4,709 |
| no `ee` at all (1996: 16, 1997: 37, 2000: 2, 2004: 24, 2005: 21) | 100 |
| an `ee` that is a Library page | 4,609 |
| of those, no 200 capture (MichelsonK06, ParkerFT06) | 2 |
| **rows of `ingest/aaai_library.toml`** | **4,607** |
| capture chosen: the latest `text/html` 200 before 2023-01-01 | 4,607 |
| capture chosen: the earliest (none before 2023) | 0 |
| capture's original URL differs from the `ee` (beyond scheme and `:80`) | 0 |

Rows by year: 1980 95, 1982 104, 1983 92, 1984 69, 1986 188, 1987 149, 1988 150, 1990 165, 1991 144, 1992 134, 1993
133, 1994 302, 1996 284, 1997 210, 1998 205, 1999 193, 2000 229, 2002 180, 2004 170, 2005 304, 2006 383, 2007 368, 2008
356. The chosen captures date from 2016 (1,010) to 2022 (1,117). The 100 records with no `ee` and the two pages with
no capture stay as they are (OpenAlex's abstract, or none); a follow-up can look for them elsewhere.

**Five captures were recorded as fixtures** (Araya84 1984, DetermanB98 IAAI 1998, KimuraSN07 2007, TaylorS06 2006's
placeholder, Lifschitz08 2008; captures from 2021-10 to 2022-12): every digest matched and none redirected, so the
late-2022 captures still hold the old layout. They are scrubbed the OJS way (decision-004: synthetic title, authors
and abstract words, the HTML structure, the placeholder and the `Subjects:`/`Submitted:` lines real;
`backend/tests/fixtures/http/aaai_library/`).

**The title check.** The page's `<h1>` must have the record's title key. dblp's titles carry OCR typos the pages
don't: 2 of the 15 sampled pages fail the check for that reason alone (aaai80-016, dblp `Optimisation … Conputer` vs
the page's `Optimization … Computer`; aaai93-015, dblp `Programrning`). So expect roughly a tenth of the pages to be
refused under an exact rule. The controller's ruling (fix round 1, decision-051): a page also attaches when the two
title keys' similarity (1 − Levenshtein / the longer) is at least 0.9 and their digit tokens agree (aaai80-016 scores
0.974); those attaches are counted `title_near` and listed by record id with their score.

**The attribution links.** A record's attribution links its dblp `ee`, AAAI's own canonical URL for the paper. On
AAAI's 2023 site those URLs may now redirect or be dead; they are kept, because they are AAAI's own, and the claim's
evidence names the capture that was read.

**As built.** `ingest/aaai_library.toml` + `aaai_library_table.py`, `sources/aaai_library.py`, `op ingest
aaai-library`, the `aaai_library` claim source (record schema 9; after `ojs`, before `openalex`), filled after dedup and
before the OpenAlex fill (spec 01 §Sources, AAAI library row). The snapshot manifest's `sources.aaai_library` carries a
`capture_window`, the range of the attached pages' capture times, and `/coverage` and a search record show that range
for the source (kind `archive_captures`), not the harvest's fetch dates: the text is from 2016–2022, not 2026 (gate C
round 1). The full harvest (about 4,607 requests, at least 3.8
hours) and the rebuild were run after review (2026-10-11); the counts:

- Harvest: 4,607 pages pinned, 0 missing, 1 unavailable because its capture redirects (`capture_redirect`).
- Snapshot `2026-10-11-93c2937e2f29` (173,253 records), index `b4f335e07e70`: `aaai_library` attached 4,536 of 4,709
  candidates (126 `title_near`), refusing `title_mismatch` 43, `layout_unknown` 23, `undecodable` 3,
  `capture_redirect` 1 and `no_abstract` 1; the capture window is 2016-05-05 to 2022-12-29. So 96.3% of AAAI 1980–2008 records have AAAI's
  own abstract.
- OpenAlex then fills only what is left: 1,117 abstracts (1,098 by DOI and 19 by title; AAAI 21, AIES 557, FAccT 539),
  with `official_won` 1,305 and refused `doi_duplicate` 1, `inverted_gap` 2, `no_abstract` 10, `title_ambiguous` 1,
  `title_unmatched` 141.
- `op snapshot diff` against `2026-10-10-9efa49481112` (before milestone C): 5,653 changed, `abstract` only
  (`abstract_kind` `none` → `official` 4,536, `none` → `openalex` 1,117); none added, removed or rekeyed.
