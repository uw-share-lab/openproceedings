# AAAI, AIES, FAccT and IASEAI — design

Status: **approved; milestone A built (2026-10-09), milestone B built (2026-10-10), milestone C planned** · Decision: decision-049 ·
Supersedes: spec 00 §Scope's venue list and the "later extension" line · Sources checked live on 2026-10-09
(facts recorded in `docs/research/2026-10-09-aaai-aies-facct-iaseai-sources.md`)

Milestones A and B as built are documented in `docs/specs/01-ingestion.md` §Sources (the OJS, dblp, PMLR, Crossref
and FAccT site rows; the "Milestone B as built" note below says where the build departs from this design). Everything
below about milestone C (OpenAlex, `abstract_kind`) is the plan, not built.

## Owner decisions (2026-10-09)

1. AAAI, AIES, FAccT and IASEAI join the corpus scope.
2. **Every paper of every year** (decision-047's full-history rule): AAAI from 1980, AIES and FAccT from 2018,
   IASEAI from its first edition with papers (2026; IASEAI '25 published none).
3. **Abstracts are searched for every paper that has one.** Precedence: the official source's abstract, else
   OpenAlex's (new venues only), else `null`. The abstract's origin is labelled, filterable and counted.
4. **Everything is indexed with its real track**; the existing default (`track:(datasets_benchmarks OR main OR
   position)`, `status:accepted`; `query/defaults.py`) is unchanged (owner, 2026-10-09, after the design first
   misstated it as `NOT track:workshop`). The new non-main tracks are excluded by default and counted in the
   exclusion buckets, as `competition` and `tiny_papers` are; one `track:` clause brings them back. Saved
   searches' canonical strings are unaffected.
5. IAAI and EAAI, printed in the AAAI volumes, are `venue:AAAI` with tracks `iaai` and `eaai`.
6. Approach: one source module per official host plus an OpenAlex abstract-fill step (approach 1 of 3; dblp
   for everything and OpenAlex for everything were rejected: the dblp release lags new years and has no AAAI
   sections, and OpenAlex has truncated and duplicate DOIs and no tracks).
7. TASK-202 (the scheduled crawl) covers every source in scope; all docs are updated as built.

## Where each venue-year comes from

| Venue | Years | Paper list | Abstract | Papers (live, 2026-10-09) |
|---|---|---|---|---|
| AAAI | 1980–2008 (none held 1981, 1985, 1989, **1995**, 2001, 2003, 2009: 23 held years) | pinned dblp release, `conf/aaai/<year>` main keys (built) | OpenAlex, else `null` (aaai.org has none and sets `Crawl-delay: 43200`); none yet (milestone C) | **4,730 as built** (4,689 main-volume entries, minus 12 not-paper rows, plus 53 workshop entries); estimated ~3.7k on 2026-10-09 |
| AAAI | 2010–2026 (Vol. 24–40) | ojs.aaai.org OAI-PMH, journal `AAAI` | official (`dc:description`) | 25,135 on the issue pages (IAAI and EAAI included) |
| AIES | 2018–2023 | Crossref, ACM proceedings DOIs 10.1145/3278721, 3306618, 3375627, 3461702, 3514094, 3600211 (built) | OpenAlex, else `null` (Crossref holds none; ACM DL is Cloudflare-challenged and excluded); none yet (milestone C) | 78, 91, 76, 114, 115, 101 = **575 as built**, all `main` (no section data: student abstracts and keynotes inside) |
| AIES | 2024–2025 (Vol. 7–8) | ojs.aaai.org OAI-PMH, journal `AIES` | official | 170, 279 (excl. front matter) |
| AIES | 2026 | not yet published (Malmö, 12–14 Oct 2026) | — | — |
| FAccT | 2018 (FAT*) | PMLR v81 (built) | official (PMLR page) | **17 as built** (preface and two keynotes excluded) |
| FAccT | 2019–2026 | Crossref, ACM proceedings DOIs 10.1145/3287560, 3351095, 3442188, 3531146, 3593013, 3630106, 3715275, 3805689 (built) | official from facctconference.org for 2022 (169 of 181), 2025 (206 of 206), 2026 (298 of 314); else OpenAlex; else `null` | 41, 95 (26 tutorial/CRAFT rows excluded: 69), 82, 181, 153, 167, 206, 314 = 1,239 DOIs, **1,213 as built**; with 2018, **FAccT is 1,230 records** |
| IASEAI | 2026 (Vol. 2) | ojs.aaai.org OAI-PMH, journal `IASEAI` | official | 57 archival (35 non-archival have no findable listing) |
| IASEAI | 2027 | OpenReview `IASEAI.org/2027/Conference` once decisions (20 Nov 2026) are public | official (OpenReview) | — (follow-up task) |

About 31k new records; the corpus grows from ~141k to ~172k. Milestone B brought 6,535 of them: AAAI 1980–2008's 4,730, AIES 2018–2023's 575 and FAccT's 1,230.

## Data model

**Venues** (`vocab.CONFERENCES`, which gives `venue_name`, export strings and year floors):

| `venue` | Name | Acronym eras | Floor |
|---|---|---|---|
| `AAAI` | AAAI Conference on Artificial Intelligence | 1980 `AAAI` | 1980 |
| `AIES` | AAAI/ACM Conference on AI, Ethics, and Society | 2018 `AIES` | 2018 |
| `FAccT` | ACM Conference on Fairness, Accountability, and Transparency | 2018 `FAT*`, 2021 `FAccT` | 2018 |
| `IASEAI` | International Association for Safe and Ethical AI Conference | 2025 `IASEAI` | 2025 |

**Native ids** in `op:<venue>:<year>:<native>`: `ojs-<article id>` (ojs.aaai.org article ids are unique across
its journals), `doi-<suffix>` for ACM (`doi-3593013.3594011`), `dblp-<key>` (AAAI 1980–2008, the key after
`conf/aaai/`), `pmlr-v81-<key>`. `urls.proceedings_native` gains the OJS and DOI rules.

**No overlap between sources:** each venue-year has exactly one paper-list source (table above), so no new
cross-source dedup is needed. The existing dedup still runs over the whole snapshot.

**Tracks:** new `Track` values `student_abstract`, `consortium` (doctoral and undergraduate consortia),
`demo`, `iaai`, `eaai` (the last two valid only for AAAI; the record refuses them on another venue). Mapping:

| `track` | AAAI | AIES | FAccT | IASEAI |
|---|---|---|---|---|
| `main` | technical tracks; special tracks (AI for Social Impact, Safe/Robust/Responsible AI, AI Alignment, focus areas); Journal Track; dblp main keys | full papers (OJS `FUL`, `A25-1..3`); all ACM papers but `not_paper` | all papers but `not_paper` | Main Track |
| `student_abstract` | Student Abstract and Poster Program | student abstracts (`STU`, `A25-SA*`) | — | — |
| `consortium` | Doctoral Consortium, Undergraduate Consortium | — | — | — |
| `demo` | Demonstration Track | — | — | — |
| `iaai` / `eaai` | IAAI and EAAI sections | — | — | — |
| `other` | Senior Member Presentations, New Faculty Highlights, Emerging Trends, any recognised section not above (label kept in evidence) | — | — | — |
| `workshop` | dblp workshop keys (`2015ethics`, `2017w`, `2021safeai`, …) | — | — | — |

Only `main` of these is in the default track filter; every other row is indexed, excluded by default and
counted (owner decision 4).

`not_paper` entries (front matter, prefaces, keynotes, tutorials, CRAFT sessions) are counted, never records.

**Status:** `accepted` for every record of these sources (none publishes rejected submissions); evidence names
the source and table row.

**Abstract precedence and `abstract_kind`:** (named `abstract_kind`, not `abstract_source`: the API's `Hit`, the CSV
column and JSONL key `abstract_source` and the RIS `N1 - Abstract source:` line already name each abstract's claim
source, e.g. `pmlr`; once `openalex` is a claim source and an `ORIGIN_NAMES` entry, exports name it with no new
column.)
- An official abstract (OJS, PMLR, facctconference.org, OpenReview) always wins; OpenAlex fills only a record
  whose abstract is still `null`, and only for AAAI, AIES and FAccT. NeurIPS, ICLR and ICML keep spec 01's rule.
- `abstract_kind` (`official` | `openalex` | `none`) is a **derived** field like `venue_name`: computed from the
  abstract's claims (`dedup.abstract_claim`: `none` without an abstract; `openalex` only when at least one claim
  holds the abstract and every such claim is `openalex`; else `official`, so a fixture without provenance is
  `official`), never stored in `records.jsonl`, so snapshot hashes and `content_hash` don't depend on it.
  `op snapshot diff` compares it on both sides, since a same-text change of source changes no hash.
- The `abstract_kind:` filter needs index schema 4 (a `SchemaForm` flag, a per-engine facet set; a query naming
  it on a schema-3 index is a 422, never a 500; schema 2 retired unless a search record pins it, per the
  index-versioning skill), so it ships in milestone C with OpenAlex: before then every value is `official` or
  `none`.
- OpenAlex abstracts pass the same hygiene as every abstract: control characters replaced, the leading/trailing
  `…` rejection, the 20,000-character and combining-mark caps.
- `RECORD_SCHEMA_VERSION` 5 → 6 (new enum values).

## Sources

All sources use the shared HTTP layer (`ingest/sources/http.py`): polite pacing, cache, robots respected.
Every claim records source, URL, fetch time and evidence. Every table is data loaded and validated by code and
pinned by tests against recorded pages; an unlisted unit (section, key, volume, DOI prefix) stops the crawl.

### 1. `sources/ojs.py` — ojs.aaai.org (AAAI 2010+, AIES 2024+, IASEAI 2026+)
- OAI-PMH, `metadataPrefix=oai_dc`, per journal (`/index.php/{AAAI,AIES,IASEAI}/oai`), following
  `resumptionToken`, in three steps: the journal-wide `ListIdentifiers` chain is the inventory (which articles exist;
  deleted headers counted from it); each of the journal's sets (`ListSets`) is read by `ListRecords&set=` for the
  metadata in bulk (inside a set, a page that answers 5xx after every retry falls back to the set's
  `ListIdentifiers` + `GetRecord`); every live inventory article no set returned is read by `GetRecord`. Why
  (found 2026-10-09): one record the server can't render (AAAI article 39173) makes its whole page answer HTTP 500
  and ends a chain; and set names are not unique (AAAI `EAAI-POS` twice, `EAAI-Full`/`EAAI-FULL` matched
  case-blind), so `set=` reaches only one of two sections. An article two set requests return is kept once (two
  differing copies stop the crawl). An article no route serves is `unavailable`: named in a `[[unavailable]]` row,
  it is listed in its volume and never a record; an unnamed one stops the crawl. A 5xx failure is cached as its
  status, so the offline replay takes the same path.
- Fields: `dc:title`; `dc:creator` in order; `dc:description` → abstract; the 10.1609 DOI → `urls.doi`; the
  article and PDF links; `dc:source` → volume and issue. Year from the volume (AAAI: volume − 1986; AIES:
  volume + 2017; IASEAI: volume + 2024), checked against the table.
- Track from the record's `setSpec` (one section each) through `ingest/ojs_sections.toml`: per journal,
  volume and section, the track, a verified count and the verification date. An unlisted section stops the
  crawl. Front-matter sections (`FMT`) and deleted headers are counted, never records.
- Each volume's record count must equal the table's verified count. The ~1,050-record gap between
  `completeListSize` (26,185) and the issue pages (25,135) is reconciled while the table is built (deleted
  headers, front matter, or a documented cause); none ships unexplained. Reconciled 2026-10-09: 26,185 = 25,136
  live + 1 unavailable (39173) + 1,048 deleted headers (stale tombstones of 448 re-published articles and one
  pre-2020 id); the issue pages total 25,136 once 2013's article 8500 (linked by public id) is counted
  (`docs/research/2026-10-09-aaai-aies-facct-iaseai-sources.md`).
- An article page is fetched only if a record lacks a required field.

### 2. dblp release, widened — AAAI 1980–2008
- `sources/dblp_xml.py`'s one streaming pass also extracts `conf/aaai/` from the already-pinned release
  (`10.4230/dblp.xml.2026-10-03`); no new download. dblp.org is still never fetched.
- `ingest/dblp_aaai.toml`: per year the main-conference keys (split years 1986, 1991, 1994, 1996 have `-1`/`-2`
  keys) with verified counts; workshop keys → `workshop`; `[[not_paper]]` rows (invited talks and similar)
  → counted. An unlisted key in 1980–2008 stops the ingest. dblp's AAAI 2010+ keys are never read (OJS owns
  those years), nor `conf/iaai`/`conf/eaai` (separate proceedings before 2010).
- Fields as for ICML: title (closing period dropped), authors (homonym numbers dropped), DOI where dblp has
  one, `urls.proceedings` the dblp record page (linked, never fetched). No abstracts.

### 3. `sources/crossref.py` — ACM proceedings (FAccT 2019–2026, AIES 2018–2023)
- Reads the proceedings record `api.crossref.org/works/10.1145/<toc>` (title, ISBN, date), then pages
  `/works?filter=prefix:10.1145,from-pub-date:…,until-pub-date:…&cursor=*`, keeping DOIs that extend
  `10.1145/<toc>.`. Sequential, with a `mailto` in the User-Agent (parallel requests get HTTP 429).
- `ingest/acm_proceedings.toml`: per venue and year the proceedings DOI, the date window, the verified count and
  `[[not_paper]]` rows (FAccT 2020's tutorials and CRAFT sessions, listed by DOI). A count mismatch stops it.
- Fields: title, authors in order, DOI, `urls.proceedings` the DOI link. No abstracts (Crossref holds none for
  these venues; checked on all 1,239 FAccT DOIs (the first count, 1,341, was not reproducible; see Milestone B as built) and 18 sampled AIES DOIs).

### 4. PMLR v81 — FAccT 2018
- A row in `ingest/pmlr_volumes.toml` (venue `FAccT`, year 2018, track `main`, 17 papers; preface and two
  keynotes excluded as `not_paper`). The existing crawler supplies abstracts.

### 5. `sources/facct_site.py` — official FAccT abstracts (2022, 2025, 2026)
- `ingest/facct_site.toml` names each page with its verified row count: `2022/acceptedpapers.html`,
  `static/docs/facct2025-final.csv` (TYPE, ID, ABSTRACT, AUTHOR, TITLE, URL), `static/docs/facct2026-final.csv`
  (Paper ID, Title, Authors, Abstract). robots.txt allows everything.
- Attached by DOI where the page has one (2025), else by exact title key with exactly one entry and one record
  sharing it (the `icml_sites` rule). Unmatched (2026's non-archival rows) and ambiguous entries are counted
  (`site_unmatched`, `site_ambiguous`), never forced.

### 6. `sources/openalex.py` — abstract fill (AAAI, AIES, FAccT)
- Only records still with `abstract = null` after every official source.
- Lookup by DOI in batches (`filter=doi:a|b|…`, ≤ 50); a dblp AAAI record without a DOI by exact title key +
  year + venue, attached only when exactly one OpenAlex work matches. A match whose DOI disagrees with the
  record's is refused and counted.
- Text rebuilt from `abstract_inverted_index` in position order. The crawl writes an extract (work id, DOI,
  abstract, fetch time) that a snapshot build replays without refetching, as the dblp extract is replayed.
- Claim: source `openalex`, url the work's API URL, evidence naming the work id and the match rule.
- Credentials (`mailto` or API key) from `.env` if OpenAlex requires them; none in code or logs.

## Query, API, exports, frontend

- **Spec 02:** `venue:` accepts the four venues (vocabulary from `vocab`); `track:` accepts the five new values;
  a new filter field `abstract_kind:` (`official` | `openalex` | `none`) filters and never matches text
  (guarantee 2), has no default, and is a fast field in the index with the same rule in the reference matcher.
- **Spec 04:** `abstract_kind` on paper and search-hit payloads; OpenAPI, frontend types and fixtures
  regenerated. RIS: the existing `N1  - Abstract source:` line names OpenAlex and the work's URL; CSV and JSONL: the
  existing `abstract_source` column says `openalex`, and a new `abstract_kind` column follows the last one. BibTeX unchanged. `venue_name` covers the new venues through `CONFERENCES`.
- **Spec 05:** seven venue chips; the coverage page counts official / OpenAlex / missing abstracts per
  venue-year, with copy on what OpenAlex is and why it is a fallback; an "abstract via OpenAlex" label on the
  paper page; CV-7's venue-span note updated.

## Evaluation and ops

- **Spec 07:** `op eval coverage --check` gains every new venue-year at its table count; the gate checks each
  count. An audit compares OpenAlex abstracts with official ones where both exist (FAccT 2022/2025/2026, AIES
  2024–2025, AAAI 2010+ sample) and reports the exact and near-exact match rates in `docs/results/`.
- **Spec 08:** `op crawl` targets `ojs`, `crossref`, `facct-site`, `openalex`; a full run orders the existing
  sources, then `ojs`, `crossref`, `facct-site`, and `openalex` last.
- **TASK-202:** the schedule runs every source in the tables; a venue's first appearance is not a per-venue-year
  drop; a new venue-year at an existing source (AIES 2026 on OJS) needs a table row, not code.
- **Follow-up task:** IASEAI 2027 via OpenReview after 20 Nov 2026, if accepted papers are public.

## Testing

Tests never reach a live service (recorded fixtures under `backend/tests/fixtures/`).
- OJS: recorded OAI-PMH pages for 2010 (three issues), 2019 (one issue), 2026 (many sections), AIES and IASEAI;
  unmapped section and count mismatch stop; resumption token followed; deleted and front-matter records
  counted; a missing `dc:description` gives `null`.
- Tables (`ojs_sections`, `dblp_aaai`, `acm_proceedings`, `facct_site`, the PMLR v81 row) loaded, validated and
  pinned against recorded pages.
- dblp: a synthetic XML with main, split-year, workshop, `not_paper` and an unlisted key.
- Crossref: recorded cursor pages; foreign DOIs dropped; `not_paper` excluded; count mismatch stops.
- FAccT site: DOI join, title-key join, ambiguous and unmatched counted.
- OpenAlex: inverted-index rebuild (repeats, gaps); DOI and title rules; ambiguous refused; never overwrites an
  official abstract; never touches NeurIPS/ICLR/ICML; hygiene.
- A property test: the official abstract wins over OpenAlex whatever the claim order.
- Query: golden cases for `abstract_kind:` and the new `venue:`/`track:` values; reference matcher and Tantivy
  agree; differential and property generators include the new field and values.
- API/exports: regenerated OpenAPI and fixtures; the RIS `N1` note; the CSV column; `venue_name` per era.
- Frontend: coverage-page and paper-label component tests; e2e for the chips; visual baselines refreshed.
- Real data (local): a live crawl; snapshot build; `op snapshot diff` (additions only, no existing record
  changed); index build; full-corpus `op index parity`; `op eval coverage --check`; the OpenAlex audit; spec 03
  benchmarks at ~172k records (a budget miss becomes its own task).

## Milestones (one PR each, focused reviewer per task, full review gate per milestone)

- **A** — decision-049, record schema 6, vocab, tracks and native ids, the `ojs` claim source, the HTTP
  layer's XML responses, `sources/ojs.py` with `ojs_sections.toml`, `op ingest ojs`, the research note, docs.
  Brings AAAI 2010+, AIES 2024+ and IASEAI 2026 (~25.5k papers). The synthetic test corpus is pinned to the
  pre-change venue and track tuples so contract fixtures and benchmarks don't reshuffle.
- **B** — dblp AAAI 1980–2008 (`dblp_aaai.toml`), `sources/crossref.py` with `acm_proceedings.toml`, PMLR v81,
  `sources/facct_site.py`.
- **C** — `abstract_kind` (derived field, index schema 4, the `abstract_kind:` filter, API, coverage, frontend), `sources/openalex.py`, the OpenAlex audit, snapshot and index build, coverage, benchmarks, TASK-202
  update, the IASEAI 2027 follow-up task, every spec and README brought to as-built.

## Risks

- The OJS count gap (above) must be explained before counts are pinned.
- AAAI section names change by year (386 sets; `AI24-n` and `AI26-n` mean different tracks), so the section
  table is hand-built and the largest review surface.
- OpenAlex abstracts are aggregated, not publisher-deposited; the audit measures their fidelity, and the label
  and filter let a review exclude them.
- Performance at ~172k records against spec 03's budgets (TASK-196's p95 history).
- Licence: OJS pages state AAAI copyright; ACM papers carry mixed CC and ACM licences; OpenAlex data is CC0.
  Indexing titles and abstracts with links back is the posture already used for PMLR and NeurIPS; the
  takedown process (spec 08) covers all venues.

## Milestone B as built (2026-10-10)

Milestone B is built ([spec 01](../specs/01-ingestion.md) §Sources: the dblp, PMLR, Crossref and FAccT site rows;
`docs/plans/2026-10-10-new-venues-milestone-b.md` is its implementation plan). The controller accepted the planner's
decisions of that plan, and these are where the build departs from, or settles, this design:

- **AAAI was not held in 1995 either.** The not-held years are 1981, 1985, 1989, 1995, 2001, 2003 and 2009 (dblp's
  titles number 1994 the 12th meeting and 1996 the 13th), so AAAI 1980–2008 has 23 held years and 4,730 records, not
  the design's 24 years.
- **dblp:** AAAI has its own extract (`<cache>/dblp/extract/aaai/<sha256>.json`) beside ICML's, which keeps its path
  and bytes; one streaming pass writes every slice that is missing. The release pin stays in `dblp_icml.toml`. AAAI's
  markers and replay are their own, and `[[not_paper]]` rows of the three new sources (dblp AAAI, Crossref, PMLR v81)
  are counted and never records, where ICML's stay `other` records. A takedown scopes a dblp id by venue
  (`aaai:dblp-<key>`).
- **PMLR v81:** a `not_papers` column holds the preface and two keynotes (`papers = 20`, 17 records); a non-ICML
  volume's count mismatch stops the crawl; a venue-tagged `PMLR_NATIVE_VOLUMES` names a v81 record, while the
  ICML-only maps and the RIS importer are untouched.
- **Crossref:** requests go one at a time with the `CROSSREF_MAILTO` User-Agent, which the controller made
  **optional** (unset: the public pool; malformed: the crawl stops, `bad_contact`). The design's "1,341 FAccT DOIs"
  was not reproducible: the ACM tables of contents hold 1,239, with no extra DOI in any window, and 575 AIES 2018–2023
  DOIs. The ISBN cross-check could not be built (the papers carry no ISBN), and the count checks the table does stand
  instead (research note §The ACM census). FAccT 2020's 26 tutorial and CRAFT rows are `[[not_paper]]`.
- **AIES 2018–2023 are all `main`**, as the design says: Crossref carries no section data, so student abstracts and
  keynotes (141 entries of two pages or fewer, listed in the research note for the owner) sit inside `main`, unlike
  2024+, where OJS labels student abstracts. The coverage page's database scope says so.
- **FAccT site:** the pages are read by `op ingest crossref` (there is no `op ingest facct-site`; spec 08's design
  target is folded into `crossref`). 2025 joins by DOI and 2022 and 2026 by exact title key, one to one, never fuzzy:
  169 of 181, 206 of 206 and 298 of 314 attach. The 2022 page's DOI links are never read (entry 295 links entry 314's).
- **Record schema 7** (decision-049): the `crossref` and `facct_site` sources, `doi-<toc>.<n>` ids (digits only) and
  `dblp-` ids for AAAI, and the `pmlr-` native id widened from ICML to FAccT (v81). A dedup idempotence bug of TASK-179's step 3 that the milestone's Hypothesis runs found is
  fixed: the forum link and steps 2 and 3 repeat until a pass merges nothing.
- **No official count rows** were added for these venue-years (spec 07 §C).
- **Real data (2026-10-10):** snapshot 2026-10-10-21779e017036 (173,292 records; diff against milestone A's
  2026-10-10-988e342c9c07 is +6,535 added, 0 changed, 0 removed), index 99c2e7ea2a0a, full parity 0 differences,
  coverage --check PASS (77/78); ICML's dblp extract hash unchanged.

Milestone C (OpenAlex and `abstract_kind`) is still planned, as above.
