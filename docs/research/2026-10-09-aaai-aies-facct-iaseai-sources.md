# AAAI, AIES, FAccT and IASEAI: sources, census and section table (checked 2026-10-09 and 2026-10-10)

This note supports `backend/src/openproceedings/ingest/ojs_sections.toml` (decision-049) and the new-venues design
(`docs/plans/2026-10-09-new-venues-design.md`).

It records four things:
- the live facts gathered on 2026-10-09;
- the ojs.aaai.org census and its reconciliation;
- two server quirks the harvest had to handle;
- the section-to-track decisions, including the sections left for the owner to review.

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
  `conf/aaai/<year>` 1980–2026, with no AAAI in 1981, 1985, 1989, 2001, 2003 or 2009. Its main keys total 28,802,
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

These facts feed milestone B, which is not built, and their evidence trail is thinner than the OJS one: the
session recorded the DOIs below and the counts, but not the exact OpenAlex queries, the CSV file URLs or a per-fact
fetch time. Each fact marked *(unverified here)* must be re-read, with its URL or query recorded, before milestone B
relies on it (TASK-214 builds it).

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
  entries above (82 more with the 2018 PMLR volume's 20); what the extra DOIs were, and how many were checked, was
  not recorded *(unverified here)*.
- facctconference.org (robots.txt allows everything) has:
  - the 2025 final CSV: 217 rows, abstracts, DOIs *(file URL not recorded; unverified here)*;
  - the 2026 final CSV: 325 rows, abstracts, no DOIs *(file URL not recorded; unverified here)*;
  - a 2022 accepted-papers page with abstracts;
  - titles only for the other years.
- The ACM DL answers 403 (Cloudflare).
- OpenAlex has abstracts for 100% of 2019–2024, 195 of 206 for 2025, and 293 of 317 for 2026 *(query not
  recorded; unverified here)*. Its DOIs are sometimes truncated or duplicated, which is the likely reason its
  counts (206, 317) differ from the ACM entries (206, 314) and the CSV rows (217, 325); the difference was not
  itemised.
- ACM has been fully open access since 2026-01-01. No metadata or abstract licence was found.

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
| `main` | 401 | AAAI technical tracks; "Technical Papers: …"; "Main Track: …"; "Main Technical Papers"; topic sections of 2010–2014 (Robotics, Knowledge Representation and Reasoning, …); special tracks (AI for Social Impact, Safe/Robust/Responsible AI, AI Alignment, the 2021 focus areas, the 2010–2016 special tracks, and the 2011 and 2013 "Robotics Program", AAAI-13's AI and Robotics special track); Journal Track; AIES full papers and main tracks; IASEAI Main Track |
| `student_abstract` | 20 | Student abstracts, including "Pre-PhD Student Abstracts" (2013) |
| `consortium` | 20 | Doctoral and undergraduate consortia |
| `demo` | 13 | Demonstrations, including "Virtual Agent Demonstrations" (2015) |
| `iaai` | 53 | IAAI sections |
| `eaai` | 52 | EAAI sections |
| `other` | 38 | Senior Member papers and presentations; "Senior Track" (2018); New Faculty Highlights; Emerging Trends; the owner-review rows below |
| `front_matter` | 4 | AAAI 2013 "Frontmatter"; AAAI 2023 "Errata" (errata notices, not papers; the owner ruled front matter); AIES 2024 and IASEAI 2026 "Frontmatter" |

The `main` and `student_abstract` rows include AIES (4 main, 3 student-abstract rows) and IASEAI (1 main row).

Per year, AAAI's `main` count is:

| Year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 |
|---|---|---|---|---|---|---|---|---|---|
| `main` | 259 | 248 | 294 | 202 | 398 | 538 | 548 | 639 | 937 |

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
- facctconference.org
- OpenAlex
- the pinned dblp release `dblp-2026-10-03.xml.gz`
