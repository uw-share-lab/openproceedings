---
id: decision-051
title: >-
  AAAI 1980-2008 abstracts come from Internet Archive captures of the old
  aaai.org paper pages, pinned by digest; aaai.org itself is never fetched
date: '2026-10-11 03:07'
status: accepted
---
## Context

After the OpenAlex fill (decision-049, milestone C), 3,648 of the 4,709 AAAI 1980–2008 records had no abstract, and
the other 1,061 had OpenAlex's, not AAAI's (TASK-232). dblp gives those years no abstracts, but each record's dblp
`ee` is its old aaai.org paper page (`www.aaai.org/Library/{AAAI,IAAI}/<yyyy>/<id>.php`), and those pages printed the
abstract. aaai.org's robots.txt asks crawlers for a `Crawl-delay` of 43,200 seconds (one request every 12 hours), and
its 2023 site dropped the Library pages. The Internet Archive holds status-200 captures of all but two of the 4,609
pages dblp links (the census of 2026-10-10, `scripts/aaai_library_census.py`): 15 of 15 sampled captures held the
abstract, and the 4 that could be checked against the live new-site abstract were identical to it. Fetching a capture
as `https://web.archive.org/web/<timestamp>id_/<url>` returns the archived bytes exactly; their SHA-1 is the digest the
archive's CDX index gives. Options considered: crawling aaai.org at its crawl delay (refused: about 6.3 years for
4,609 pages), the PDFs (refused: text extraction, and the same copyright), leaving the records `none` or OpenAlex's
(refused: AAAI's own text exists and is official), and the archived pages (chosen). The owner approved on 2026-10-10.

## Decision

We read AAAI 1980–2008 abstracts from Internet Archive captures of the old aaai.org paper pages, as a new official
claim source, `aaai_library`.
- **aaai.org is never fetched.** The only host is `web.archive.org`, for the captures and for the CDX index the
  census reads (two requests). This sidesteps the crawl delay and puts no load on aaai.org; the archive is read one
  request at a time, at least 3 seconds apart, with the repo's generic User-Agent and no contact string.
- **Each record is pinned to one capture** by URL, timestamp and SHA-1 digest in `ingest/aaai_library.toml`: the
  latest text/html 200 capture before 2023-01-01, else the earliest. Bytes with another digest are refused
  (`digest_mismatch`), at harvest and again at every build; no other capture is ever read in its place.
- **The join is exact**: the record's dblp key, through the `ee` dblp itself gives. The page's `<h1>` title is checked
  too (the controller's ruling, review round 1, refined by the reviewer): the abstract attaches when the two title
  keys (`dedup.title_key`) are equal; else when their similarity, 1 − Levenshtein distance / the longer key's length,
  is at least 0.9, counted `title_near` and listed in the fill report with the record id and its score (dblp's OCR
  typos, `Optimisation … Conputer`, score about 0.97); never when their digit tokens differ (`Part 1` against `Part
  2`), whatever the score; otherwise it is refused (`title_mismatch`). Placeholders (`None - 2 page paper is an
  abstract`), empty texts and texts under 40 characters are `no_abstract`. Every refusal is counted.
- **Precedence**: after `ojs`, before `crossref`, `facct_site`, `ris` and `openalex`. The fill runs after dedup and
  reconcile and before the OpenAlex fill and takedowns, so an AAAI page's abstract fills a record first, OpenAlex
  fills only what the pages leave null, and a takedown still withholds it. A record OpenAlex filled before becomes
  `abstract_kind` `official`.
- **Copyright and attribution**: the text is AAAI's copyright, served on the same posture as the ojs.aaai.org
  abstracts already served (decision-018, the takedown list, TASK-135). The attribution names AAAI and links the
  aaai.org page (the dblp `ee`), never the archive's copy; the claim's url is the capture and its evidence names the
  `ee`, the timestamp and the digest. The `ee` links are AAAI's own canonical URLs for the papers and are kept as
  the attribution, though on AAAI's 2023 site they may now redirect or be dead.
- **A redirected capture** (the controller's ruling, 2026-10-10, after the live harvest stopped at row 374 on a 302:
  the CDX lists some captures as 200 that `id_` replay redirects to another timestamp, a revisit or warc-dedup
  record) is handled deterministically, never followed blindly and never a silent fallback. At most one redirect is
  followed, and only to `https://web.archive.org/web/<14-digit timestamp>id_/<the same page>` (http/https and `www.`
  normalised, the same path), its host checked by the shared client; its bytes attach only when they hash to the
  row's pinned digest (the same content, deduplicated), cached under the row's capture key and counted
  `redirected_same`. Other bytes, another URL or host, a second redirect or no `Location` record the row as
  unavailable: the 3xx is kept in the cache like a 404/410, so the build knows it offline, and it is counted
  `capture_redirect` on the INFO and attention lines. A redirect never stops the harvest, which is complete with such
  rows; the fill counts them, never `not_cached`.

## Consequences

`record.Source` gains `aaai_library` (record schema 9); the model refuses it on any field but `abstract`, any venue
but AAAI and any record but a dblp one. `op ingest aaai-library` caches the captures (about 4,607 requests, at least
3.8 hours at 3 s) and writes a marker; `op snapshot build` reads them offline and reports the fill in the manifest
(`sources.aaai_library.fills`). Record content changes, so a new snapshot and index change `snapshot_hash`, and
records saved on an earlier index replay as `drifted`. 100 records have no `ee` at all and two pages have no capture:
they stay as they are (OpenAlex's, or `none`). dblp's titles carry OCR typos the pages don't (2 of the 15 sampled
pages: `Optimisation`/`Optimization`, `Programrning`), so the near-title rule above attaches those and counts them (`title_near`).
The harvest's marker names the sha256 of `aaai_library.toml`; a build refuses a marker for another table, or one that
names none (`harvest_stale`: re-run `op ingest aaai-library`). Revisit if the archive withdraws captures (the build stops on a missing or changed one: re-run
the census), if AAAI publishes these abstracts on its new site, or if AAAI asks for them to be taken down.

