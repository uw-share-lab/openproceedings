# NeurIPS 1987–2012 and ICML 1988–2012: sources, checked live

Status: verified 2026-10-06/07 (TASK-204, TASK-205, TASK-206; decision-047) · the facts behind spec 01 §Sources'
NeurIPS, dblp and ICML sites rows, `ingest/dblp_icml.toml` and `ingest/icml_sites.toml`

The owner decided on 2026-10-06 to index the full history of NeurIPS (from 1987) and ICML (from 1988), superseding
decision-013's 2013 floor. ICLR is unchanged: it began in 2013.

## NeurIPS 1987–2012: the proceedings site

`proceedings.neurips.cc` serves a year page for every year from 1987. The 1987–2012 pages have the shape of 2013's:
`ul.paper-list` of `<li data-track="none">` entries, `span.paper-count` (`90 papers` in 1987), token-less
`-Abstract.html` links, and abstract pages with `citation_title`, `citation_author`, `citation_pdf_url` and
`p.paper-abstract`. So `classify.classify_neurips_listing`'s host-and-year rule (no token up to 2021: `main`)
already covered them, and the only change was the miner's floor (`neurips.FIRST_YEAR`, 2013 → 1987). The 1987
year and abstract pages are recorded, scrubbed, as `backend/tests/fixtures/http/neurips/1987/`.

Per-year counts are in the table at the end (§NeurIPS per year).

Old abstracts are PDF-extracted text, with the extractor's artifacts: `(cid:173)` where a soft hyphen broke a word
at a line end (`non(cid:173) linear`), other `(cid:N)` codes for glyphs it couldn't map, doubled spaces and the odd
split word. The tokenizer read `(cid:173)` as the tokens `cid` and `173`, so `nonlinear` didn't match
`non(cid:173) linear`; 1,676 of the 4,821 records have at least one code, nearly all from 1987–2002. 1987–2012 pages
also show the placeholder `Abstract Unavailable` where a paper has no abstract (55 records have none).

Both are cleaned at ingest (decision-047, spec 01 §Pipeline 2), as decision-044 cleans control characters:
`(cid:173)` and the whitespace after it are removed (`princi(cid:173) ples` → `principles`), any other code becomes
a space, and the claim's evidence and the listing's `abstract_pdf_codes` count them; the placeholder is no abstract
(counted missing). Abstracts under five words, extractor fragments such as an author's name, are kept and counted
(`abstract_short`, 15). No page from 2013 on holds a code or a placeholder.

## ICML 1988–2012: the pinned dblp release

PMLR has no ICML volume before v28 (2013). The earlier proceedings are scattered: icml.cc/2012/papers and
icml.cc's copies of the 2008–2011 sites survive (2007: its paper list only); 2004–2008 are in the ACM DL (whose terms forbid scraping); earlier years
were Morgan Kaufmann print. dblp indexes them all, but:

- **dblp.org forbids crawling.** Its `robots.txt` is `User-agent: * / Disallow: /`, and its HTML pages and search
  API sit behind an Anubis bot challenge (checked 2026-10-06). dblp.org is never fetched; a record's dblp page is
  only linked (`urls.proceedings`).
- **The sanctioned bulk route** is dblp's monthly snapshot XML release on Dagstuhl DROPS
  (`https://drops.dagstuhl.de/entities/collection/10.4230/dblp.xml`), CC0, one DOI per release. DROPS's
  `robots.txt` disallows only `/api/*` and metadata paths.

Pinned (`ingest/dblp_icml.toml`):

| | DOI | File | Size | sha256 | md5 (DROPS) |
|---|---|---|---|---|---|
| Release (October 2026) | `10.4230/dblp.xml.2026-10-03` | `https://drops.dagstuhl.de/storage/artifacts/dblp/xml/2026/dblp-2026-10-03.xml.gz` | 1,107,081,001 | `20e45961bec5610dc07b8e932ccd27a2387534cfa12c92a24289fe873aebe969` | `cbd329100ea1bbb2873fa2f6d414ea00` |
| DTD | `10.4230/dblp.xml.dtd.2023-06-28` | `https://drops.dagstuhl.de/storage/artifacts/dblp/xml/2023/dblp-2023-06-28.dtd` | 13,134 | `03ec35cb34a4227572a0e89da407b06b6e44a6cc23e19cabc3b49b702a5f897d` | `96e4283e71886dec2173718957293648` |

The release names its DTD by file name (`<!DOCTYPE dblp SYSTEM "dblp-2023-06-28.dtd">`) and spells non-ASCII
characters as the DTD's entities. Its framing: a record's end tag and the next record's start tag often share a
line (`</incollection><inproceedings …>`), so the reader finds start tags anywhere in a line. Reading its 17,115
`conf/icml/` records (50 proceedings, 17,065 inproceedings) by streaming takes about 75 s.

### Which `conf/icml/` proceedings are the main conference

Every `conf/icml/` proceedings record dblp dates 1988–2012, and how the table classifies it:

| Key | dblp year | Papers | Classification |
|---|---|---|---|
| `conf/icml/1988` … `conf/icml/2012` | the conference year | 2,676 in all (below) | each year's main conference |
| `conf/icml/2006sna` | 2007 | 17 (dated 2006) | excluded: ICML 2006 Workshop on Statistical Network Analysis (Springer LNCS) |
| `conf/icml/2010ltr` | 2011 | 0 | excluded: Yahoo! Learning to Rank Challenge at ICML 2010 (JMLR W&CP 14) |
| `conf/icml/2011otee` | 2012 | 0 | excluded: On-line Trading of Exploration and Exploitation 2 workshop at ICML 2011 |
| `conf/icml/2011utl` | 2012 | 0 | excluded: Unsupervised and Transfer Learning workshop at ICML 2011 |

1989, 1991 and 1992 were held as the International Workshop on Machine Learning (ML 1989, ML91, ML 1992), the
series' meeting in those years: `vocab.CONFERENCES` counts ICML from 1988, its 5th meeting, so they are its main
conference. No `conf/icml/` inproceedings of 1988–2012 lacks a crossref.

Not every entry under a main-conference key is a paper. 2009's key holds 9 "Workshop summary:", 9 "Tutorial
summary:" and 2 "Invited talk:" entries (180 entries; the conference's own page lists 160 papers), and 1994–1996
hold one-page invited-talk abstracts (`Pereira94`, `Croft95`, `Heckerman95`, `Pomerleau95`, `Mannila96`, `Moore96`,
`Vapnik96`). The table lists these 27 as `[[not_paper]]` rows: they are records of track `other`, which the default
`track:main` leaves out and the exclusion banner counts. Found by the review gate (2026-10-07) by reading every
title with "summary", "invited", "tutorial", "panel" or "(Abstract)" and every one-page entry; no other year has
such entries. ICML 2010's seven invited application papers (IDs 901–907 on the official page, two of them
two-page entries in dblp: `Apte10`, `FelzenszwalbGMR10`) are papers the conference listed with abstracts, so they
stay `main`. dblp's `conf/icml/2013` (283) onward is
PMLR's, never read, so dblp and PMLR never hold the same venue-year. 2009 has one paper with
`publtype="withdrawn"`, counted and not a record.

`ee` links of the 2,676 papers: 1,291 DOIs (Morgan Kaufmann/Elsevier `10.1016/b978-…` for 1988–2002, ACM
`10.1145/…` for 2004–2009), 554 icml.cc (2010–2012 PDFs), 117 AAAI pages (2003), 90 wikidata and 1 ORKG entry
(dropped). 618 author names carry a dblp homonym number (` 0001`), dropped.

## Per year: records, abstracts and where they came from

`op ingest dblp --year 1988-2012`, 2026-10-07 (the abstract sources: `2026-10-06-icml-pre-2013-abstract-sources.md`).
"Unmatched" counts page entries whose title key no record of the year has: the title differs ("Online Learning of
Pseudo-Metrics" on the 2004 page is "Online and batch learning of pseudo-metrics" in dblp), or the paper is no record
(2009's withdrawn paper, whose page entry is the removal notice). No near title is ever matched. "Dropped" (2007: 1)
counts an entry whose abstract page is empty (paper 394).

| Year | dblp papers | Records | With an abstract | Without | Page entries | Unmatched | Ambiguous | Source |
|---|---|---|---|---|---|---|---|---|
| 1988–2000 | 960 | 960 | 0 | 960 | — | — | — | none |
| 2001 | 80 | 80 | 79 | 1 | 79 | 0 | 0 | Purdue site, capture 20010708012312 |
| 2002 | 87 | 87 | 0 | 87 | — | — | — | none |
| 2003 | 117 | 117 | 116 | 1 | 118 | 2 | 0 | HP Labs site, capture 20030628150843 |
| 2004 | 117 | 117 | 112 | 5 | 118 | 6 | 0 | Banff site, capture 20040907123036 |
| 2005 | 134 | 134 | 0 | 134 | — | — | — | none |
| 2006 | 140 | 140 | 0 | 140 | — | — | — | none (17 workshop papers excluded) |
| 2007 | 150 | 150 | 140 | 10 | 149 (1 dropped) | 9 | 0 | icml.cc list + 150 Oregon State captures (5 served as UTF-8) |
| 2008 | 157 | 157 | 153 | 4 | 158 | 5 | 0 | icml.cc |
| 2009 | 180 | 179 | 153 | 26 | 160 | 7 | 0 | icml.cc (1 withdrawn paper not a record; 20 records are summaries or talks, track `other`) |
| 2010 | 159 | 159 | 151 | 8 | 159 | 8 | 0 | icml.cc |
| 2011 | 152 | 152 | 144 | 8 | 152 | 8 | 0 | icml.cc |
| 2012 | 243 | 243 | 242 | 1 | 243 | 1 | 0 | icml.cc |
| **all** | **2,676** | **2,675** | **1,290** | **1,385** | | | | |

1988–2000 by year: 1988 49, 1989 128, 1990 50, 1991 128, 1992 60, 1993 44, 1994 45, 1995 71, 1996 66, 1997 48,
1998 66, 1999 54, 2000 151 (each equal to the table's verified count).

## NeurIPS per year

`op ingest neurips --year 1987-2012`, 2026-10-06/07: 4,847 requests (26 year pages, 4,821 abstract pages), no
retry; counts as `op snapshot build` replays them with decision-047's cleaning. Every year's listing matched its
stated count; no page was missing and no title mismatched.

| Year | Listed (= the page's count) | Records | No abstract | (cid:N) repaired | Short (<5 words) |
|---|---|---|---|---|---|
| 1987 | 90 | 90 | 8 | 46 | 5 |
| 1988 | 94 | 94 | 10 | 54 | 2 |
| 1989 | 101 | 101 | 3 | 73 | 0 |
| 1990 | 143 | 143 | 1 | 94 | 2 |
| 1991 | 144 | 144 | 1 | 114 | 1 |
| 1992 | 127 | 127 | 1 | 98 | 0 |
| 1993 | 158 | 158 | 12 | 123 | 0 |
| 1994 | 140 | 140 | 2 | 110 | 0 |
| 1995 | 152 | 152 | 5 | 123 | 1 |
| 1996 | 152 | 152 | 0 | 128 | 0 |
| 1997 | 150 | 150 | 0 | 132 | 0 |
| 1998 | 151 | 151 | 1 | 125 | 0 |
| 1999 | 150 | 150 | 0 | 131 | 0 |
| 2000 | 152 | 152 | 1 | 133 | 0 |
| 2001 | 197 | 197 | 2 | 90 | 0 |
| 2002 | 207 | 207 | 2 | 55 | 1 |
| 2003 | 198 | 198 | 1 | 21 | 2 |
| 2004 | 207 | 207 | 0 | 4 | 0 |
| 2005 | 207 | 207 | 0 | 7 | 0 |
| 2006 | 204 | 204 | 2 | 4 | 1 |
| 2007 | 217 | 217 | 0 | 9 | 0 |
| 2008 | 250 | 250 | 0 | 1 | 0 |
| 2009 | 262 | 262 | 0 | 0 | 0 |
| 2010 | 292 | 292 | 0 | 0 | 0 |
| 2011 | 306 | 306 | 0 | 1 | 0 |
| 2012 | 370 | 370 | 3 | 0 | 0 |
| **all** | **4,821** | **4,821** | **55** | **1,676** | **15** |
