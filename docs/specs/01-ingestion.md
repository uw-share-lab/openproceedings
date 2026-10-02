# 01 — Ingestion

Status: **draft for review** · depends on: nothing · consumed by: 03 (index build), 04 (coverage)

## Purpose

Produce a **corpus snapshot**: one normalized record per paper, with an exact venue, year, track and
acceptance status, from every source that holds these venues. The snapshot is the only input to the index
build.

## Record schema (`PaperRecord`, pydantic v2)

| Field | Type | Notes |
|---|---|---|
| `id` | str | Stable ID `op:<venue>:<year>:<native>`, e.g. `op:iclr:2024:iilhN2MycO`. `native` is the OpenReview forum ID, or `pmlr-v202-<key>` (ICML) / `nips-<hash>` (NeurIPS; `nips-<hash>-round1`/`-round2` on the 2021 Datasets and Benchmarks host: the suffix is the link's round token, because that host numbers each round and the main track separately, so its hash alone can name three papers; a D&B link without a round, or dated other than 2021, gets no id (miner `no_round`, RIS `unresolved`), never a bare `nips-<hash>`; `urls.proceedings_native` is the one rule) / `iclr-<hash>` (ICLR) for proceedings-only papers. |
| `title` | str | Raw, whitespace-collapsed. Normalization for search happens in 03, not here. The snapshot build caps it at 1,000 characters and 8 combining marks per run (§Pipeline 2, decision-026); the model doesn't check this. |
| `abstract` | str \| null | Raw. `null` if no source has it. Never a Scholar snippet (reject values that start or end with `…`; an ellipsis inside is allowed). Never an empty string. The snapshot build caps it at 20,000 characters and 8 combining marks per run (§Pipeline 2, decision-026); the model doesn't check this. |
| `authors` | list[str] | Display order. |
| `venue` | enum | `NeurIPS` \| `ICLR` \| `ICML`. Extensible. |
| `year` | int | Conference year, not the arXiv year. A year before the venue was held under its name (NeurIPS 1987, ICLR 2013, ICML 1988; `vocab.CONFERENCES`) is refused. |
| `track` | enum | See the taxonomy below. Never defaults to `main`. Unknown stays `unknown`. |
| `status` | enum | `accepted` \| `rejected` \| `withdrawn` \| `desk_rejected` \| `unknown` |
| `presentation` | str \| null | `oral` / `spotlight` / `poster`, when the source states it (§Presentation). |
| `venue_id_raw` | str \| null | OpenReview `content.venueid` verbatim, e.g. `NeurIPS.cc/2023/Track/Datasets_and_Benchmarks`. |
| `urls` | object | `forum`, `pdf`, `proceedings`, `doi`, each optional. |
| `keywords` | list[str] | Stored and displayed, **not searched** (guarantee 2). |
| `provenance` | list[Claim] | For each field: the source, URL, fetch time and evidence (scholarmend's claim/ledger pattern). Two claim fields are provenance only, never a record field (record schema 4, decision-029): `twin`, the ids of a v1 copy's linked twins (§Pipeline, TASK-159), and `invitation`, a v1 note's OpenReview submission invitation from scholarmend 0.1.5 (§Sources, RIS row; TASK-157). |
| `content_hash` | str | sha256 of the canonical JSON of the searchable and filterable fields. |
| `venue_name` | str | **Derived, never stored** (TASK-112): the venue string of spec 04 §Exports, `vocab.venue_name(venue, year)`, e.g. `International Conference on Learning Representations (ICLR 2024)`. A pydantic computed field: sent wherever the record is (`GET /papers/{id}`'s `paper`), left out of `records.jsonl` (`record.DERIVED`, `snapshot.record_line`), so snapshots, their hashes, `RECORD_SCHEMA_VERSION` and `content_hash` don't change, and stored data that names it is refused as an extra field. |

## Track taxonomy

| `track` | Source signal |
|---|---|
| `main` | `<Venue>.cc/<Y>/Conference` (accepted), PMLR main ICML volume, NeurIPS main proceedings |
| `datasets_benchmarks` | `NeurIPS.cc/<Y>/Track/Datasets_and_Benchmarks` (2021 as `…/Round1`, `…/Round2`; 2022–2023) or `NeurIPS.cc/<Y>/Datasets_and_Benchmarks_Track` (2024–2025); NeurIPS ≤2023 proceedings `Datasets_and_Benchmarks` aliased to `_Track` (scholarmend fix); 2021 on its own host (`datasets-benchmarks-proceedings.neurips.cc`, `-round1`/`-round2`). NeurIPS 2026 renamed the track `NeurIPS.cc/2026/Evaluations_and_Datasets_Track` (a live group; TASK-094 maps it here as the same track under a new name) |
| `position` | `ICML.cc/<Y>/Position_Paper_Track` (2025+); `NeurIPS.cc/<Y>/Position_Paper_Track` (2025+, verified 2026-09-27; TASK-094). ICML 2024's position papers carry `ICML.cc/2024/Conference` with no marker, so they are `main` on OpenReview and `unknown` from PMLR v235 |
| `workshop` | `<Venue>.cc/<Y>/Workshop/…`, including satellite paths like `Workshop_Mexico_City/…` |
| `competition` | `NeurIPS.cc/<Y>/Competition_Track` (2024+; TASK-094), `NeurIPS.cc/<Y>/Track/Competition`, PMLR competition volumes (v123, v133, v176, v220) |
| `tiny_papers` | ICLR Tiny Papers (2023–2024) |
| `blogpost` | ICLR Blogpost track |
| `other` | A recognised track not listed above. Keeps `venue_id_raw` for audit. |
| `unknown` | No trustworthy signal. Always shown in coverage reports. |

The rule is carried over from scholarmend: **only `content.venueid` on the submission note decides the track
and status.** A venue must never be derived from an invitation. Doing that once turned a rejected ICLR paper
into an ICLR main-track paper (scholarmend note, `zkNCWtw2fd`). **In API v1 years the venueid is not status
evidence** (verified 2026-09-27, `docs/research/2026-09-27-openreview-and-proceedings-facts.md`): ICLR 2017,
2022 and 2023, NeurIPS 2021–2022 and D&B 2021 put the bare venue path on rejected submissions too. There the
status comes from `content.venue` (`ICLR 2022 Submitted`, `Submitted to ICLR 2023`), the decision note, or
the withdrawn / desk-rejected invitation, and the venueid only confirms venue, year and track (TASK-095).
`classify_venueid` returns status `unknown` for any venueid in a v1 venue-year (ICLR 2013–2023, NeurIPS
2021–2022: `classify.is_v1`), and `classify_v1_venue` maps the exact `content.venue` strings seen live
(an unlisted string is `unknown`).

### Status handling (decision-012)

| `status` | v2 (2023/2024+) | v1 (≤2023) | Proceedings, PMLR |
|---|---|---|---|
| `accepted` | bare venueid (`ICLR.cc/2025/Conference`) | accept decision or venue string (`ICLR 2021 Poster`, `NeurIPS 2022 Accept`, ICLR 2013 `conferenceOral-iclr2013-conference`) | listed |
| `rejected` | `…/Rejected_Submission` | reject decision, `… Submitted` / `Submitted to …` venue | never |
| `withdrawn` | `…/Withdrawn_Submission` | the `…/-/Withdrawn_Submission` invitation | never |
| `desk_rejected` | `…/Desk_Rejected_Submission` | the `…/-/Desk_Rejected_Submission` invitation | never |
| `unknown` | `…/Submission` (under review) or no venueid | no decision (ICLR 2014: `submitted, no decision`; ICLR 2023 Tiny Papers) | never |

Every public submission is ingested and indexed whatever its status; the default `status:accepted`
(02 §Default filters) excludes the others and counts them. What is public differs: ICLR publishes every
rejected, withdrawn and desk-rejected submission; NeurIPS and ICML only rejected papers whose authors opt in
(NeurIPS 2024 main: 201; ICML 2025: 162; ICML 2023–2024: none), and almost no withdrawn ones. So a status
count is complete for ICLR and a floor elsewhere, and coverage (07 §C) says which.

### Presentation (TASK-101)

`presentation` is `oral`, `spotlight`, `poster` or `null`. It is display metadata: never a track (an oral is
`main`), not in `content_hash`, and never a filter. It is set only where a source states it:

- **API v1:** the decision note, or `content.venue` for the years whose venue string names it
  (`ICLR 2017/2021/2022 {Oral,Spotlight,Poster}`, `ICLR 2023 poster`, `NeurIPS 2021 {Oral,Spotlight,Poster}`;
  `openreview_v1._PRESENTATION`).
- **API v2:** `content.venue` on an **accepted, non-workshop** submission note (track and status still come
  from `content.venueid` alone), matched exactly in its venue-year's table, `classify.V2_PRESENTATION`
  (string → the track its venueid must give, presentation). Wording and case drift every year, so it's a
  table, never a regex, and the match is byte-exact: no strip, no case-fold, no whitespace collapse
  (`ICLR 2024 Oral` is not `ICLR 2024 oral`). A string the table lacks, or lists under another track, or an
  accepted note with no string `content.venue` at all, is **unmapped**:
  `presentation` null, a DEBUG `openreview_presentation_unmapped` line with the forum id (never the string,
  which can be free text), and one count per venue-year, `presentation_unmapped`, in the crawl report, the
  `openreview_crawl_finished` line and the crawl's one `openreview_crawl_attention` WARNING. Rejected,
  withdrawn, desk-rejected and `unknown` notes are never looked up (a venue string can't promote a status),
  nor are workshop notes: a workshop's oral is not the conference's.
- **Proceedings, ICLR archive, RIS:** not set by these importers.
- **After dedup** (`dedup.resolve`): presentation follows the OpenReview-first order but status follows the
  proceedings-first order, so a record keeps its presentation only while its resolved status is `accepted`.
  A record reconcile demotes to `unknown` (OpenReview-accepted, not in the crawled proceedings), or any other
  non-accepted status, shows `null`; the presentation claim stays in provenance as evidence.

The v2 table, with each string's count of accepted submission notes in the TASK-054 crawl cache
(2026-09-29); every string has a recorded note under `backend/tests/fixtures/http/openreview/v2/`:

| Venue-year | `oral` | `spotlight` | `poster` | Stated, no presentation (`null`) |
|---|---|---|---|---|
| ICLR 2024 | `ICLR 2024 oral` 86 | `ICLR 2024 spotlight` 367 | `ICLR 2024 poster` 1,807 | `BT@ICLR2024` 22 (blogpost); `Tiny Papers @ ICLR 2024 {Archive 55, Present 98, Notable 39}` (tiny papers' tiers) |
| ICLR 2025 | `ICLR 2025 Oral` 213 | `ICLR 2025 Spotlight` 380 | `ICLR 2025 Poster` 3,110 | `ICLR 2025 Blogpost Track` 49 |
| ICLR 2026 | | | `ICLR 2026 Poster` (fixture only; not crawled) | |
| ICML 2023 | `ICML 2023 OralPoster` 155 | | `ICML 2023 Poster` 1,673 | |
| ICML 2024 | `ICML 2024 Oral` 144 | `ICML 2024 Spotlight` 191 | `ICML 2024 Poster` 2,275 | |
| ICML 2025 | `ICML 2025 oral` 108; position `… Position Paper Track oral` 12 | `ICML 2025 spotlightposter` 211; position `… spotlightposter` 12 | `ICML 2025 poster` 2,938; position `… poster` 49 | |
| NeurIPS 2023 | `NeurIPS 2023 oral` 67; D&B `NeurIPS 2023 Datasets and Benchmarks Oral` 10 | `… spotlight` 378; D&B `… Spotlight` 22 | `… poster` 2,773; D&B `… Poster` 290 | |
| NeurIPS 2024 | `NeurIPS 2024 oral` 61; D&B `NeurIPS 2024 Track Datasets and Benchmarks Oral` 11 | `… spotlight` 326; D&B `… Spotlight` 56 | `… poster` 3,648; D&B `… Poster` 392 | `NeurIPS 2024 Competition Track` 16 |
| NeurIPS 2025 | `NeurIPS 2025 oral` 77; D&B `NeurIPS 2025 Datasets and Benchmarks Track oral` 7; position `NeurIPS 2025 Position Paper Track Oral` 9 | `… spotlight` 687; D&B `… spotlight` 56 | `… poster` 4,522; D&B `… poster` 434 | `NeurIPS 2025 Position Paper Track` 31 |

ICML 2023's `OralPoster` and ICML 2025's `spotlightposter` are orals and spotlights that also had a poster
slot; the higher tier is the presentation (ICML 2023: 155 + 1,673 = the 1,828 accepted notes). No accepted,
non-workshop string in the cache is unmapped. Known unmapped strings, left out until someone can say what
they mean: `ICML 2026 regular` (recorded; not a presentation word) and ICLR 2026's `Oral`, ICML 2026's
`spotlight` (seen live 2026-09-27, research doc, but with no recorded note yet); each is counted when those
years are crawled.

## Sources

| Source | Covers | Access |
|---|---|---|
| OpenReview API v2 (`api2.openreview.net`) | ICLR 2024+, NeurIPS 2023+ (with 2023 D&B), ICML 2023+ | Authenticated with `.env` credentials (`OPENREVIEW_USERNAME`, `OPENREVIEW_PASSWORD`). Anonymous requests get HTTP 200 with an HTML browser-challenge page, never JSON (verified 2026-09-27), so a non-JSON response is an auth failure. `limit` ≤ 1000; `count` only when `offset` is sent. |
| OpenReview API v1 (`api.openreview.net`) | ICLR 2013, 2014, 2016–2023 (2016: workshop track only), NeurIPS 2021–2022 (main and D&B) | Same login. Status comes from decision notes, `content.venue` or `content.decision` (2013), never the bare venueid (§Track taxonomy). A per-year adapter handles each schema. ICLR 2014 has no decisions, ICLR 2015 is not on OpenReview, and ICLR 2016 has only its workshop track there; the ICLR archive supplies accepted conference papers for all three gaps. |
| ICLR archive (`iclr.cc/archive`) | Accepted main-conference papers for ICLR 2014–2016 | Public conference-proceedings and accepted-paper pages (`ingest/sources/iclr.py`). Only the conference sections are mined: the 2015 workshop section is excluded, and duplicate oral/poster links collapse by target. A linked OpenReview forum keeps its forum id; any other target becomes `iclr-<sha256(canonical-target)[:32]>`. The archive supplies title, authors, `main` and `accepted`, but no abstract. Recorded live counts are 35, 31 and 80 unique conference targets. |
| NeurIPS proceedings (`proceedings.neurips.cc`) | NeurIPS main, 2013 to the latest published year (2025 on 2026-09-27), and D&B 2022+; 2021 D&B on `datasets-benchmarks-proceedings.neurips.cc`. The only source before 2021 | Year index pages plus abstract pages (`ingest/sources/neurips.py`). The URL has no track token before 2022, so a token-less listing on the main host up to 2021 is `main` by host and year; the 2021 D&B host's `round1`/`round2` are `datasets_benchmarks`; `Datasets_and_Benchmarks` is the ≤2023 alias (`classify.classify_neurips_listing`, each rule named in the track claim's evidence). An abstract is taken only when the page's `citation_title` is the listed title. In 2025 the year index holds Creative AI and its known `vol38-main-conference` page holds main, D&B and position papers; the crawler follows both and reports any other unknown “See also” page. Also cross-checks OpenReview acceptance. |
| PMLR (`proceedings.mlr.press`) | ICML 2013–2022 (v28, v32, v37, v48, v70, v80, v97, v119, v139, v162); confirms 2023–2025 (v202, v235, v267) | Volume index plus per-paper pages (`ingest/sources/pmlr.py`). The volume table is data, `ingest/pmlr_volumes.toml` (venue, year, track, role, verified paper count, heading, index title, verified date, source per row), loaded and checked by `ingest/volumes.py` and pinned by tests against the recorded index and volume pages. A volume the table lacks, or lists as competition or workshop (`out_of_scope`), is never crawled or imported as ICML; a volume whose page heading the table doesn't name stops the crawl. A volume that mixes main and position papers (v235, v267) gives track `unknown`. |
| RIS importer (`ingest/ris.py`) | The Trust-Evals corpus (M2 bootstrap): two searches, 2025–26 and 2020–24, one scholarmend output each | Reads a `mended.ris` with `scholarmend.parse.parse_file` (pinned `scholarmend` PyPI package, 0.1.5) and the `resolved.json` beside it, entry by entry (a count or title mismatch is an error). Only scholarmend's identifying claims decide identity, track and status: a venueid plus its forum id; else a NeurIPS/ICLR `proceedings_url` claim (`nips-`/`iclr-<hash>`, or `nips-<hash>-round1`/`-round2` on the 2021 D&B host, all from `urls.proceedings_native`; claims naming more than one native id are `ambiguous`, so the same hash on the main and D&B hosts or in both rounds is two papers, and a 2021 D&B URL without a round is `unresolved`, never a bare `nips-<hash>`); else a `pmlr_url` claim in an ingested ICML volume of the volume table (`pmlr-v<N>-<key>`, year and track from `ingest/pmlr_volumes.toml`; since task-053 that includes v28–v97, so a URL in ICML 2013–2019 now imports where it used to be skipped as `no_id`/`out_of_scope`, a change a snapshot diff shows). A NeurIPS listing's track token must agree with the claim by the miner's host/year rules (`classify_neurips_listing`: the 2021 D&B host's `round1`/`round2` are D&B). `status` comes from a claim only: a venueid → its status, except that a v1 venue-year's venueid gives none (TASK-095; audit in `docs/results/2026-09-27-v1-status-audit.md`): there the status comes from scholarmend's `venue_string` claim (OpenReview's `content.venue` verbatim, source `openreview_api`, evidence `venueid=<id>`; added in scholarmend 0.1.4, TASK-098) through `classify_v1_venue`, used only when every such claim's evidence names the record's venueid and the string names the venueid's venue, year and track, with status evidence `scholarmend:openreview_api venueid=<id> venue_string=<string>`; otherwise, or with no such claim (entries scholarmend cached before 0.1.4 hold only a venueid), the status is `unknown` and its evidence reads `venueid=<id> (API v1 venue-year: not status evidence[; venue_string not used: <why>])`. Outside v1 years the claim is ignored. ICLR 2017's and 2013's lower-case `conference` venueids (`classify.V1_TRACK_FROM_VENUE`) name no track (`other`; 2017 puts it on workshop invitations too), so there the string's venue and year must match the venueid's (the venueid names no track to match) and the string gives the track as well (no 2013 string is in the v1 table, so a 2013 record stays `other`/`unknown`), the track claim carrying the same `venue_string` evidence (TASK-142: `ICLR 2017 Poster` → `main`/`accepted`, `ICLR 2017 Invite to Workshop` → `workshop`/`unknown`); every other `other` venueid keeps `other`; a proceedings listing → `accepted`, overriding a venueid that names the same venue, year and track (decision-005); a listing that disagrees makes the record a `conflict`. scholarmend 0.1.5's `invitation` claim names the note's OpenReview submission invitation (its top-level `invitation`, verbatim, source `openreview_api`, evidence `venueid=<id>`; TASK-157). It is used only when every such claim holds one string and names the record's venueid, and is then kept as an `invitation` claim (evidence `scholarmend:openreview_api venueid=<id>`). Through the v1 crawler's own rule (`openreview_v1.is_twin_outcome`, `submission_listing`), a main-track outcome on a note of a non-main submission listing, where the venueid names no track, is its conference twin's: the record takes that listing's track and an `unknown` status, with track and status evidence `… venue_string=<string> invitation=<inv> (the main track's outcome, not this <track> submission's)`. So a 2017 workshop copy of a rejected paper (`Submitted to ICLR 2017`, 18 on the 2026-09-29 crawl) imports as `workshop`/`unknown` as the crawler reads it (a re-import of an RIS-only snapshot with 0.1.5 claims moves up to 18 records from ICLR 2017 main/rejected to workshop/unknown, which `op snapshot diff` shows; cite the snapshot hash), where it used to import as `main`/`rejected` with claims equal to a real rejection's (TASK-152). An entry scholarmend cached before 0.1.5 has no such claim and is read as before. In a snapshot with the ICLR 2017 v1 crawl, the crawl's record wins anyway by forum-id merge (decision-005). The committed Trust-Evals cache predates 0.1.5, so no current record carries the claim. Never inferred from appearing in Scholar. Abstract: OpenReview's, else the proceedings page's, else `null` (never Scholar's or Semantic Scholar's). Authors from `AU` without Scholar's `...`. Every claim has `source = "ris"`, its origin in `evidence`, and `fetched_at` from the `M1` Query date, which Publish or Perish writes in local time with no zone: converted to UTC with the offset `ingest/ris_offsets.toml` records for the cache entry (both Trust-Evals searches at −04:00, from PoP's own epoch query records; TASK-077, decision-025), or, for an entry not in the table, kept as local wall time labelled UTC and marked local (the report's `utc_offset` null; the manifest's `query_dates` `{"ris": "local"}`, else `"utc"`), since such a date can be a day off near midnight. Skipped records are counted by reason (`out_of_scope`, `unresolved`, `no_id`, `ambiguous`, `conflict`, `no_query_date`) in an `ImportReport`; none is given a minted id. A proceedings listing whose URL year is before its venue was held under its name (`papers.nips.cc/paper/1986/…`, `proceedings.iclr.cc/paper/2012/…`) is `unresolved`: skipped and counted, never an abort of the whole file. |

For RIS URL/track agreement, both NeurIPS and ICLR proceedings claims must match the resolved track.
NeurIPS uses the same host/year/token classifier as the miner; only the pre-2022 main-host form may be
tokenless and still claim `main`. A disagreement is a `conflict`, never an inferred correction.

The M2 bootstrap is deliberately the existing corpus: the Trust-Evals review's Scholar results as
scholarmend mended them: 1,834 records read and 1,805 imported, all accepted, since the review had already
screened them; 90% main track, the rest D&B (160), position (16), one other and one workshop
(`docs/results/2026-09-27-corpus.md`). This lets the team use the engine for the live review before the
full crawl lands in M4. **Its counts are not PRISMA identification numbers:** the corpus is already the
output of a search and a screening, so `identified` and `excluded` on an M2 index describe that corpus,
not a database; cite them only once the M4 crawl indexes the proceedings themselves.

**Crawl window (decision-013):** every venue from 2013, ICLR's first year, to the current year, wherever
a source above holds the venue-year; a year range is the query's `year:` filter, never a crawl limit. The
facts in this table were checked live on 2026-09-27 (`docs/research/2026-09-27-openreview-and-proceedings-facts.md`).

## Pipeline

1. **Fetch.** One crawler per source, all on one HTTP layer (`ingest/sources/http.py`, TASK-103): every call
   goes through a disk cache keyed by the canonical URL (and, for an API, its sorted parameters), written
   atomically; only the source's hosts are called and no redirect is followed; one pacing and retry rule set
   honours `Retry-After` and `ratelimit-reset`; the sources differ only in their `Policy`. A crawl can resume.

   **Cache expiry (TASK-102).** Each `Policy` has a TTL per URL (`Policy.ttl`). A live crawl re-fetches an
   entry older than its TTL, overwrites it and logs its policy's `cache_expired` event (`crawl_cache_expired`,
   `openreview_cache_expired`; `url`, `age_s`, `ttl_s`). A policy's event names (`http.PolicyEvents`: also
   `*_retry_wait` and `*_budget_wait`) are fixed constants, never built from a prefix (TASK-116).
   An offline client (`--offline`, `--dry-run`, `op snapshot build`) never expires anything, so a replay is a
   function of the cache and rebuilds the same bytes whenever it runs; `--refresh` still re-fetches at once.
   A venue-year is *open* until the end of its calendar year (its decisions may still be out, a withdrawal
   or an opted-in rejected paper may still appear) and *over* after that:

   | Listing | Open | Over | Why |
   |---|---|---|---|
   | OpenReview v2 accepted venueid (`/notes?content.venueid=<Venue>.cc/<Y>/Conference`) | 7 days | 365 days | Grows once, at decisions; camera-ready edits until the conference; then settled |
   | OpenReview v2 submission, rejected, withdrawn, desk-rejected venueids | 1 day | 90 days | Change until decisions; an opted-in rejected paper can appear later |
   | OpenReview v2 groups (a year's groups, a venue's group) | 1 day | 90 days | A workshop added; a venue's venueids |
   | OpenReview v2 request naming no venue-year | 1 day | 1 day | Unclassified: the shortest |
   | OpenReview API v1 (every request) | never | never | Its venue-years (ICLR ≤2023, NeurIPS 2021–2022) are over and v1 is frozen |
   | ICLR archive, NeurIPS proceedings, PMLR (index and abstract pages) | never | never | Effectively immutable once published; a newly published year is `--refresh` |

   A listing is re-fetched as a whole: once one page of it expires, every later page is fetched again too,
   so its pages agree (`count`, rows and ids; a mismatch is still refused, re-run with `--refresh`).
2. **Normalize.** Map each source's shape to `PaperRecord`. Strip HTML. Keep LaTeX verbatim (03 decides
   how it is tokenized). Then the **ingest caps** (`ingest/caps.py`, decision-026, TASK-155), applied once to
   every source's records before dedup (`snapshot.load_sources`), bound what the tokenizer's NFKC reordering
   can cost. That cost is superlinear in a long run of marks with alternating combining classes.
   - **Marks.** A run of combining marks in a title or abstract keeps 8 marks, and the rest are dropped.
     - A mark is a character whose NFKD form starts with a non-zero canonical combining class.
     - A run is the marks after one base character, or at the start of the text. It is counted in NFKD
       non-starters, the base's own included.
     - A base is a letter or digit that is not a mark and that the tokenizer keeps (its LaTeX mask,
       `normalize.latex_mask`).
     - Any other character neither counts nor ends a run, because the tokenizer joins a word across the
       invisible characters and the LaTeX markup it drops (zero-width joiner, soft hyphen, `\-`, the letter of
       an accent macro such as `\H{…}`).
     - A run over the cap has its base (NFD) and marks (NFKD) decomposed in canonical order, and keeps its first
       8. Every other character is kept as it was. Trimmed text is then tidied: a title is
       whitespace-collapsed, and an abstract is stripped of whitespace and `…` at both ends, as the record
       requires.
       So every Unicode form of the same text trims alike, and dedup title keys that matched still match.
     - No token holds more than 8 consecutive non-starters, so NFC stays linear.
   - **Length.** A title keeps at most 1,000 characters and an abstract at most 20,000, counted in NFKD.
     - The cut falls before the last space that fits, so every Unicode form keeps the same words. With no space,
       it falls before the last base that fits.
     - It runs before the mark cap.
     - A cut title is whitespace-collapsed. A cut abstract is stripped of whitespace and `…` at both ends. The title cap was the
     owner's decision of 2026-10-02. The longest real title is 192 characters.

   The record's field and every claim of it are trimmed alike. A trimmed claim's `evidence` carries the note
   `trimmed at ingest (decision-026): <what>`: the marks dropped, and the length it was cut from and to. The
   note is the whole evidence when the source gave none, or follows the source's evidence in parentheses. The
   manifest names the records (`trimmed`, §5), and the build logs a `snapshot_trimmed` warning with the count.
   Text within both caps is unchanged. Snapshot 2026-09-29-d552baa07aed has none over them (decision-026): its
   longest abstract is 4,995 characters and its longest run of marks is 1. It rebuilds byte-identically. Two
   sources' texts that differ only past a cap compare equal once trimmed, so they get no `conflicts.csv` row;
   their claims still carry the note.
3. **Classify.** Derive `track`, `status` and `presentation` using the rules above. Every classification
   records its evidence claim.
4. **Deduplicate.** The same paper appears on OpenReview and in the proceedings (NeurIPS, ICML 2023+).
   `ingest/dedup.py`. Merge on (a) an identical id (the same forum ID in the same venue and year, or the
   same proceedings id), then (a′) the forum link (TASK-105): records naming the same OpenReview forum id,
   as their id or in a `urls.forum` claim (PMLR's index links the forum from ICML 2023), merge in the same
   venue and year whatever their titles say; a link across venue-years, against the track rule below, or
   shared by two listings is a `conflicts.csv` row, never a merge. Then (b) a normalized title (the token contract over the title's NFC form, so every canonically equivalent spelling, NFC, NFD or marks stored in another order, has one key: TASK-168) with the same venue and year. Two
   records are merged **only** when venue and year agree. That lesson comes from venuetriage: records
   with no year must never merge on `(title, "")`. **Two OpenReview records with different forum IDs are
   never merged** (the API v1 crawl has already collapsed two notes of one identical paper, TASK-125, and a silent twin into its accepted note, TASK-132), nor a listing linking one forum with a note of another: a main-track paper and its same-year workshop version can share a title. Title
   matching only links records *across* sources (OpenReview ↔ proceedings ↔ RIS), never joins two different
   proceedings papers, and never breaks the **track rule**: a merge that involves a proceedings listing holds
   only `main`, `datasets_benchmarks` and `position` records (a mixed PMLR volume's own `unknown` included,
   never an `unknown` an OpenReview claim gives, TASK-174), or
   only NeurIPS Creative AI records (TASK-137). The NeurIPS proceedings host Creative AI, which the taxonomy
   files under `other`; a record counts as Creative AI only when every source claiming its track claims `other`
   and backs it with the `NeurIPS.cc/<Y>/Creative_AI_Track` venueid (any status suffix) or a
   `-Creative_AI_Track` proceedings URL of the same year. Every other track (workshop, tiny papers, blogposts,
   competition, any other `other` such as `Education_Program`, a note's `unknown`) never merges with a listing,
   and the two families never mix. When a title group holds a listing, a note that can't be the listed paper (a
   track the rule keeps from every listing in the group, or rejected, withdrawn or desk-rejected: proceedings list
   only accepted papers; an `unknown` track or status stays a rival) is no rival for it (TASK-126): the rest merge
   if they may, and that note stays its own record with a `conflicts.csv` row. A merged record's fields are re-resolved from the union of its claims by the decision-005 precedence table. Track is decided
   per track (decision-005, the owner's decision of 2026-09-29): the proceedings decide a paper's track wherever
   OpenReview doesn't hold that venue-year's track (ICLR 2016 main, from the archive, stays `main`), and an
   OpenReview track claim, the note's own `content.venueid`, wins wherever the record carries one. Within a track
   OpenReview holds, a record with no merged note takes its listing's track (the owner's second answer,
   2026-09-29). Merges are written
   to `merges.csv`, and disagreements and refused merges to `conflicts.csv`, for audit (dedup-rules skill).

   **Reconcile** (`ingest/reconcile.py`, TASK-072, decision-005). Where a venue-year's official proceedings
   are crawled completely (every listing states a count and matched it, every entry became a record, and no
   volume it names was left uncrawled), an
   OpenReview-accepted record in a track those listings hold (`main`, `datasets_benchmarks`, `position`; a
   listing's own track, or for a mixed PMLR volume the track of the record it merged into) that merged with no
   listing and shares no title key or forum id with one gets `status=unknown`: an absence claim from the
   proceedings source (`status=unknown`, the listing's URL, its index-page fetch, evidence `not listed: …`)
   that outranks OpenReview, so the record still equals what its claims resolve to, and its
   `precedence:<source>` `conflicts.csv` rows, one per OpenReview source whose status claim differs, which
   replace the record's earlier `precedence:` status rows as dedup run again would write them (TASK-154). The
   OpenReview claims are kept. An absence claim never makes a record a listing, so dedup run again changes
   nothing, and reconcile is idempotent. A venue-year with an incomplete listing, a track no listing holds,
   and a record sharing a title or forum with a listing it didn't merge with (ambiguous: it may be the listed
   paper) are left alone. The check on the 2026-09-29 crawl is
   `docs/results/2026-09-29-reconcile-real-data.md`.
5. **Snapshot.** Write `data/snapshots/<date>-<shorthash>/records.jsonl` (sorted by `id`) and
   `manifest.json`. The manifest holds counts per venue × year × track × status, source versions,
   the crawl date and the snapshot hash. Snapshots are immutable. `data/` is gitignored. Since manifest
   format 2 (TASK-082) it also holds, per venue × year × track, the missing abstracts and the claim
   sources of its records; per claim source, its crawl window; and per venue-year, the **statuses
   indexed** (spec 07 §C). A build withholds every abstract on the deployment's takedown list (spec 08
   §Deploy, decision-022): the record keeps everything but its `abstract` (null) and its abstract claims,
   and the manifest names those ids (`withheld`) and counts them per venue-year and track
   (`abstract_withheld`, `abstract_withheld_by_track`), apart from the missing abstracts. When the ingest caps
   trimmed any title or abstract claim of a record (§2, decision-026), `trimmed` lists those ids, sorted. A
   claim that precedence overruled counts. A record whose takedown withheld its only trimmed claim does not. The key is
   absent when nothing was trimmed, so it is additive with no format bump. With any RIS
   report it also holds `query_dates: {"ris": "utc" | "local"}`: `utc` only when every RIS report has a
   recorded `utc_offset` (its Publish or Perish query dates converted to UTC). A manifest without the key
   reads as local. The key is additive, with no format bump (TASK-077, decision-025). Its `merges` and `conflicts` count the rows of `merges.csv` and `conflicts.csv`:
   `conflicts` is `total` plus one count per resolution kind present (the part of `resolution` before any
   `:`): `precedence` (a field decided by the source precedence table, `precedence:<source>`, reconcile's
   absence claims included), `newest` and `tie` (one source gave two values for a field: `newest:<source>` when the newest was kept, `tie:<source>`
   when both were fetched at the same moment),
   `ambiguous_not_merged`, `track_not_merged` and `venue_year_not_merged` (merges refused), and `unresolved`
   (`unresolved:<source>`: one source's own signals disagree, so the field is `unknown`; decision-020). A kind
   with no rows is absent, not 0.

**Statuses indexed** are which statuses a venue-year's sources can contain at all, from the source table in
`ingest/statuses.py` (`SOURCE_STATUSES`, one row per claim source): an OpenReview venueid can carry every
status (`classify_venueid`), a proceedings listing only `accepted` (`classify_proceedings`), and the RIS
bootstrap, which resolves through either, every status where OpenReview holds the venue-year and only
`accepted` elsewhere. Whether OpenReview holds a venue-year comes from the API v1 adapters (excluding empty
ICLR 2015) and the API v2 first-year table, and a test pins those definitions together. The snapshot build records them per venue-year,
the table's statuses plus any status the venue-year's records hold, so a later change to the table never
rewrites an existing snapshot.

   The build also checks each venue-year's statuses against what its claim sources can supply
   (`ingest/status_check.py`, TASK-109, using the same `ingest/statuses.py` table: OpenReview every status; a proceedings listing `accepted` only; RIS
   every status where OpenReview holds the venue-year, else `accepted`). Each (venue, year, status) its
   records hold that none of its sources can supply is logged (`snapshot_unexpected_status`) and listed with
   its record ids in `op snapshot build`'s output (`unexpected_statuses`). It points at a classification
   error; it is a report, never a refusal, and never changes the snapshot's bytes.

## CLI

```
op ingest openreview --venue ICLR --years 2020-2026
op ingest iclr --year 2014-2016 [--dry-run | --offline] [--refresh] [--delay 1]
op ingest neurips --year 2013-2025 [--dry-run | --offline] [--refresh] [--delay 1]
op ingest pmlr --year 2013-2025 [--dry-run | --offline] [--refresh] [--delay 1]
op ingest ris <mended.ris>...           # cache scholarmend outputs (resolved.json beside each)
op snapshot build [--from <cache>]      # merge sources → new immutable snapshot
op snapshot diff <a> <b>                # added / removed / changed records
```

As built (task-022, task-050, task-051, task-052/053, task-096): `ingest ris`, `ingest openreview`,
`ingest iclr`, `ingest neurips`, `ingest pmlr`, `snapshot build` and `snapshot diff`. `ingest openreview` (task-050 API v2: ICLR 2024+, NeurIPS
2023+, ICML 2023+; task-051 API v1: ICLR 2013–2023, NeurIPS 2021–2022; each year goes to the API that holds it,
and a year on neither, such as NeurIPS 2020, refuses the whole request before anything is fetched) takes `--venue`,
`--years YYYY[-YYYY]` (or `--year`) and one of `--offline` (replay the cache; a miss is refused), `--dry-run` (no
network and no writes: prints each venue-year's report with `complete: false` and the first uncached request of
each branch in `would_fetch`) or `--refresh` (fetch every response again). A v2 year lists the year's groups
(`Workshop`, `Workshop_<City>` and `Track` are expanded; proposal groups and groups that aren't v2 venues are
skipped and reported), then every venue's accepted, submission, rejected, withdrawn and desk-rejected venueids
(decision-012), 1,000 notes a page sorted by `number`. A v1 year runs its adapter (`openreview_v1.ADAPTERS`, one
per venue-year schema): it lists the year's exact submission, withdrawn and desk-rejected invitations
(`?invitation=`, 1,000 a page, `count` checked), takes status from `content.decision` (ICLR 2013), `content.venue`
(`classify_v1_venue`: ICLR 2017, 2022, 2023, NeurIPS), the decision note fetched per forum (`?forum=`; ICLR
2018–2020, and 2021 notes without a venue string) or the withdrawn / desk-rejected invitation, never the v1
venueid; status evidence naming the main track on a note of a non-main listing, where the venueid names no track,
is read as its conference twin's outcome (for ICLR 2017, each such note's `_bibtex` names its twin), so the note
keeps its listing's track and its status is `unknown`, counted in the report's `twin_outcome` (a manifest key
present only when non-zero: 18 for ICLR 2017, its workshop copies of rejected papers that say `Submitted to ICLR
2017`; TASK-152, `docs/results/2026-10-01-iclr-2017-workshop-copies.md`); a venueid that names a track is still
checked against the string's, a disagreement a conflict; ICLR 2014 and 2016 have no decisions (`unknown`), and ICLR
2015 has nothing to crawl. What OpenReview can't answer for a year is listed in the report's `coverage_gaps`, never
raised. A note whose own evidence disagrees (the withdrawn ICLR 2021 note `xGZG2kS5bFk` says `ICLR 2021 Poster`;
two decision notes that disagree; a venueid naming another track) gets `unknown` for that field and an
`unresolved:openreview_v1` row in `conflicts.csv` (counted as `unresolved` in the manifest's `conflicts`). No signal outranks another
(decision-020): `xGZG2kS5bFk` was withdrawn yet presented at ICLR 2021, while ICLR 2018's `S1p31z-Ab` was
accepted by its decision note yet withdrawn and not presented, so any fixed ranking is wrong for one of them.
The same holds across two notes of one paper: an accepted record whose pdf a withdrawn record of the same
crawl and the same track shares (`S1p31z-Ab` and its withdrawn twin `SJTCsqMUf`) becomes `unknown` with an
`unresolved:openreview_v1` row naming every such twin, and the twins keep their own status (`withdrawn_twins`, run
after the listings and before the collapse below). A desk-rejected twin does not count (a desk rejection for a
duplicate submission can leave the same pdf beside the presented copy), nor does a twin in another track (a
workshop version of a conference paper), nor a record with no OpenReview pdf. A record with **no decision at all**
(no decision note in its forum) and such a twin has one status signal, the twin's withdrawal, so it becomes
`withdrawn` (the owner, 2026-09-29, TASK-139: ICLR 2018 main's 12 undecided blind notes), with no conflict row
since nothing disagrees; its status claim cites the twin's listing page and names every twin
(`no decision note in the forum; withdrawn twin <id> shares the pdf (invitation=…)`). The crawl report moves each
such note out of `unmapped` (where its missing decision note was counted) into `withdrawn_by_twin` (a manifest key
present only when non-zero: 12 for ICLR 2018), so the attention warning and the coverage report's crawl listing no
longer report it. A rejected record with a
withdrawn twin stays `rejected` (10 in ICLR 2018), a record `unknown` for any other reason (a conflict, an unmapped
string, `Invite to Workshop Track`) stays `unknown`, and the twins are the records withdrawn by their listing
before the rule runs, so its result doesn't depend on order and a second run changes nothing. A record the rule
touched is never collapsed below. **Authors** (decision-019): `content.authors` is split into names only when the split
can be checked. A list with no entry starting with `and ` and none joining two names with ` and ` is kept as
listed, whatever its length. Otherwise (one string, as early ICLR 2017 writes it, or a list with such an entry)
each entry loses a leading `and ` (a bare `and` entry becomes nothing) and a dangling trailing ` and`, and is
split at `, and `, `,` and ` and ` (lowercase `and` only); the split is kept only when it gives exactly as many
names as the note's `authorids` (or its `author_emails`, a list or one comma-separated string, when there are no
ids) and no name still needs splitting. A refused split leaves the authors empty; either way the authors claim's
evidence keeps the raw value, and the report counts `authors_split` and `authors_unsplit`, listing the refused
notes in `authors_unsplit_ids` when there are any. **Two notes of one paper are one record** (TASK-125): API v1 holds 300 NeurIPS 2021 main-track
papers twice, as two Blind_Submission notes with different ids and numbers whose content is identical but for
the id embedded in `_bibtex` (e.g. `-K4tIyQLaY` #292 and `BW2Z6B7S9KZ` #8244), which dedup would refuse as two
submissions with one title. After a v1 venue-year's listings, records identical in everything but their id,
forum URL and provenance (title, authors in order, abstract, keywords, pdf, track, status, presentation,
venueid, all exact), each with a pdf and an integer note `number` and no crawl conflict, are collapsed to the
lowest-numbered note (a deterministic tie-break whatever the listing order, not "the original": the NeurIPS
2021 proceedings link the kept forum for 177 of the 297 accepted pairs and the dropped one for 120); every other note is counted in the
report's `skipped.duplicate_submission`, a DEBUG `openreview_duplicate_submission` line and the crawl's
`openreview_crawl_attention`. **A silent twin** (TASK-132) is the one exception to "identical": in a year whose
one status carrier is `content.venue`, a note with status `unknown` and neither a non-null `venue` nor a
non-null `venueid` says nothing about its status. After the identical notes collapse, such a note is dropped
(counted the same way) when exactly one other record with a pdf is identical to it in everything but status,
presentation and venueid, and that record is `accepted` with no crawl conflict: no absence of evidence
contradicts an acceptance, while a second such record (with evidence or with a conflict), or a rejection, would
be a choice. The kept record is the accepted one whatever the numbers. A note the identical-note collapse kept
is silent only if every note it stands for is (TASK-147): one that absorbed a note with a non-null `venue` or
`venueid` (even `''`) stays a separate `unknown` record beside the accepted note (removed by the default status
filter and itemised in `excluded.status.unknown`), so the tie-break between two identical notes never decides
whether a third, accepted one absorbs them. On the 2026-09-29 crawl this is one pair: NeurIPS 2021 `W6e384Lkjbw`
#5999 (no venue; the proceedings link it) and `rDdb26AQ0SO` #11021 (`NeurIPS 2021 Poster`), with the same pdf,
supplementary material, title, authors, abstract and keywords, so the paper merges with its proceedings record.
Notes differing in any other compared field (another pdf; ICLR 2018's blind vs withdrawn copies of one pdf) stay
separate, and a note without a pdf is never collapsed. API v2 has no such notes (the 2026-09-29 crawl) and doesn't
run this rule. **A copy and its main-track twin are two linked records** (TASK-159, decision-029; the owner,
2026-10-02):
- **What a copy is.** A record from a non-main submission listing whose dedup title key is that of exactly one
  record from the main-track submission listing is a copy of it. With several such records, it is a copy of the
  one its `_bibtex` url names.
- **Why `_bibtex` is checked against the title.** ICLR 2017's 35 `Invite to Workshop` notes all carry a
  `_bibtex` naming one unrelated forum, so a `_bibtex` counts only when its forum has the copy's title.
- **Never merged.** The two are different submissions with their own outcomes. Each gets one `twin` claim, a
  tuple of the other records' ids, sorted, with its own title claim's url and fetched_at, and evidence saying
  whether `_bibtex` or the title alone linked them (`link_twins`, after the collapses).
- **Counted.** The crawl report's `twins_linked` counts the copies linked, with a DEBUG `openreview_v1_twin_linked`
  line each. Its `twins_ambiguous` counts the copies left unlinked because several main-track submissions share
  their title and their `_bibtex` names none, with a DEBUG `openreview_v1_twin_ambiguous` line each. Both are
  manifest keys present only when non-zero: 53 and absent on the 2026-09-29 crawl.
- **On the 2026-09-29 crawl,** only ICLR 2017 has copies. 53 workshop notes (18 `Submitted to ICLR 2017`, 34
  `Invite to Workshop`, 1 with no venue) link to 51 conference notes, 104 records in all.
- **Effect on records.** Tracks, statuses, hashes and counts are unchanged; the claim is provenance only
  (`docs/results/2026-10-02-iclr-2017-twins.md`).
- **Shown** (TASK-162). Each result and the paper page say "See also (the same paper's other record): `<id>`",
  each id a link to its paper page; the API sends the ids as `twins` and every export names them (spec 04
  §Exports: an RIS `N1`, BibTeX `openproceedings_twins`, a CSV column, a JSONL list). The provenance table still
  shows the claim.
- **Taken down together** (TASK-163, owner decision 2026-10-02). A takedown follows a twin link: listing either
  copy withholds both abstracts, at serve time and in a snapshot build, and the operator lists and logs both ids
  (spec 08 §Deploy).
- **Checked.** A snapshot refuses a `twin` claim naming a record it doesn't hold.
- **Reporting.** Linked twins are two records identified, as before. The tool removes neither before screening.
  Exports carry both, each naming the other (TASK-162), so a reviewer's own duplicate step can see why a
  same-title pair is there; one it drops belongs in the review's own "duplicates removed" count.

Responses are cached under
`<data-dir>/cache/openreview/{v2,v1}/http/` (the shared `{key, payload}` cache contains only a versioned,
world-readable projection; restricted fields are removed before persistence and older raw entries are
invalid; a v1 client logs in on api2, whose token api1 accepts) and a finished
venue-year writes `…/{v2,v1}/crawls/<Venue>-<Year>.json`, which `snapshot build` replays offline. A note or group is world-readable when its
`readers` are a list of strings naming `everyone` and its `nonreaders` are absent, `null` (API v1 writes it on
public notes) or a list of strings not naming `everyone`; any other shape is refused. Code:
`ingest/sources/openreview_client.py` (OpenReview's policy and login on the shared HTTP layer),
`ingest/sources/openreview_v2.py` (enumeration, records) and `ingest/sources/openreview_v1.py` (the per-year
adapters). `op --data-dir <dir> <command>` (a global option; default `$OP_DATA_DIR`, else the repository's
`data/`, gitignored); results go to stdout as JSON, a refusal exits 1 with a one-line reason that never
quotes record text.

The proceedings crawlers (`ingest/sources/`): `--year` takes a year or an inclusive range and repeats.
Every request goes through the page cache `<data-dir>/cache/{iclr,neurips,pmlr}/pages/` (one JSON entry per
URL, fixture-shaped, written atomically, with the fetch time every claim carries), one request per second
per crawl by default (`--delay`, never under 0.5 s), retrying 429/5xx with `Retry-After` and refusing
other 4xx at once, on the source's own hosts only. A crawl resumes from the cache; when a listing's
pages are all cached it writes a marker (`<cache>/<source>/crawls/<year|vN>.json`), and `op snapshot
build` re-mines every marked listing from the cache alone, so a snapshot never fetches. `--dry-run` reads
only the index pages and reports what a crawl would fetch (`to_fetch`); `--offline` reads only the cache;
`--refresh` re-fetches index pages (a year published since). `ingest pmlr` maps a year to its ICML volume
through the volume table and refuses a year the table lacks. Each listing's report (stated vs listed
count, tracks, abstracts missing and why, unknown tracks, crawl window) goes into the manifest's `sources`
under `iclr_archive` / `neurips_proceedings` / `pmlr`. The ICLR archive accepts only 2014–2016 and mines
the public accepted-paper listing itself, so its records intentionally retain `abstract=null`.

**Crawl logs** (TASK-116; logging-standards skill §Crawl lines). A crawl logs a start line, heartbeats and an
end line at INFO: `openreview_crawl_started` / `openreview_crawl_progress` (at most every 30 s of the HTTP
client's monotonic clock, with `api`, `venue`, `year`, the counts so far, `requests` and `cached`) /
`openreview_crawl_finished` (also `cache_incompatible`: pre-projection cache entries purged and re-fetched,
each a DEBUG `openreview_cache_incompatible` line); `neurips_listing_started` / `neurips_listing_progress` / `neurips_listing_mined`
and the `pmlr_volume_*` equivalents. A record-level anomaly (an unknown track, an unmapped status string, a
duplicate, a record that won't build) is DEBUG; each listing or crawl logs at most one aggregate WARNING with
the counts (`listing_attention`, `openreview_crawl_attention`), beside listing-level ones such as
`listing_count_mismatch`. A proceedings page past the HTML parser's bounds (`html.HTMLBudgetError`, reason
`html_budget`) names its URL and how to recover (an index page: `--refresh`; a paper page: delete its cache
entry, `pages/<sha256[:2]>/<sha256>.json`); on a paper page it is counted as `invalid`, on a listing page it
refuses the crawl.

## Error handling

- Missing abstract: keep the record with `abstract=null`. It is still matched on title. Count it in the
  manifest.
- Unparseable venueid: `track=unknown`, logged, and surfaced on the coverage page. Never guessed.
- A source disagrees with another (for example, OpenReview says accepted but the proceedings don't list
  it): keep both claims, set `status` from the higher-priority source, and write `conflicts.csv`. The
  per-field precedence table is decision-005: OpenReview first for title, abstract and authors (the
  proceedings only where OpenReview lacks the paper); the official proceedings decide acceptance where
  they are published and crawled (OpenReview-accepted but unlisted → `unknown` + a conflict row; §Pipeline 4,
  Reconcile); OpenReview's venueid decides track, and status elsewhere. A title that differs between merged sources is a conflict row too.

## Testing

- Recorded HTTP fixtures (VCR-style) for each source and each year's schema variant, recorded by hand
  and scrubbed of real text (titles, abstracts, authors replaced; structure kept, including the separators
  between author names and the count of a comma-separated email string, which the v1 author splitter reads),
  per decision-004.
- A venueid-parsing table test covering every venueid form seen in scholarmend's 90 validated cases, plus
  the known workshop forms.
- Dedup property tests. Never merge across venue or year. Merging is idempotent and order-independent,
  and never folds two forum ids (own or linked). The forum link has table tests from the recorded v235
  index and ICML 2024 note (`test_dedup_forum_link.py`).
- Reconcile table and property tests (`test_reconcile.py`): only unlisted OpenReview acceptances in a covered
  track of a completely crawled venue-year change, only to `unknown`; conflicts rows only appear, except a
  changed record's superseded `precedence:` status rows, whose non-`unknown` values its new rows still name
  (TASK-154); dedup and reconcile run again change nothing.
- Snapshot determinism: the same inputs give a byte-identical `records.jsonl` and hash.
- Proceedings miners (`test_iclr.py`, `test_neurips.py`, `test_pmlr.py`, `test_fetch.py`): the recorded
  ICLR archive, NeurIPS year/volume, and PMLR year/paper pages seeded into a page cache, including the
  NeurIPS 2025 split listing, PMLR v202/v267 forum links, and a real double-escaped author; plus a scripted
  transport for the fetcher (pacing, `Retry-After`, 4xx,
  truncation, off-host redirects, resume after a failure). Scrubbing gave each abstract page another
  synthetic title than its listing, so a case needing them to agree edits the recorded page and says so;
  the untouched page is the title-mismatch case.
