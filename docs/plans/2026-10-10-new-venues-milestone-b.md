# New venues, milestone B (AAAI 1980–2008 from dblp, FAccT and AIES from Crossref, FAccT 2018 from PMLR, official FAccT abstracts): implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task by task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fill the venue-years that milestone A left empty:
- AAAI 1980–2008 (with no AAAI in 1981, 1985, 1989, 2001, 2003 or 2009), from the pinned dblp release;
- FAccT 2019–2026 and AIES 2018–2023, from Crossref's records of the ACM proceedings;
- FAccT 2018 (FAT\*), from PMLR v81;
- the official FAccT abstracts for 2022, 2025 and 2026, from facctconference.org.

This adds about 5.5k records. OpenAlex and `abstract_kind` are milestone C.

**Architecture:** Each piece follows the closest existing pattern.
- **dblp (AAAI).** The streaming reader learns to read several key prefixes in one pass (`dblp_xml.read_streams`). AAAI gets its own extract file beside ICML's, which keeps its path and bytes. A new table (`ingest/dblp_aaai.toml`, loaded by `ingest/dblp_aaai_table.py`) and a new miner (`sources/dblp_aaai.py`) are replayed through their own `Crawls`.
- **PMLR.** `volumes.py` and `pmlr.py` accept one non-ICML ingested venue (FAccT), behind an explicit allowlist. Every ICML structure stays as it is.
- **Crossref.** `sources/crossref.py` pages Crossref's `/works` with a cursor, one request at a time through the shared HTTP layer. The User-Agent carries a `mailto` read from `.env`. It is driven by `ingest/acm_proceedings.toml` (loaded by `ingest/acm_table.py`).
- **FAccT site.** `sources/facct_site.py` reads the official FAccT pages that `ingest/facct_site.toml` names. `op ingest crossref` fetches them, and `crossref.mine_proceedings` joins them to records by DOI or by exact title key, as `icml_sites` is joined inside `dblp.mine_year`.

Every record is built from claims (`common.record_from_claims`) and replayed offline by `op snapshot build` through `crawl.SOURCES`.

**Tech Stack:** Python 3.12, pydantic v2, stdlib `csv`, `json`, `html` and expat. No new dependency. tomllib, pytest + hypothesis, uv. Frontend: one `ORIGIN_NAMES` entry pair only.

**Spec:** `docs/plans/2026-10-09-new-venues-design.md` (binding; this plan implements its milestone B). Live facts: `docs/research/2026-10-09-aaai-aies-facct-iaseai-sources.md`. Repo rules: `CLAUDE.md`, `docs/specs/01-ingestion.md`.

## Controller rulings (binding; override the planner decisions and task text below where they conflict)

- All planner decisions below are accepted except where these rulings say otherwise.
- `CROSSREF_MAILTO` is **optional**. If it is unset, the User-Agent carries no `mailto` (Crossref's public pool) and a live crawl
  proceeds; it never stops with `no_contact`. The owner approved a contact address, and it is
  stored only in the gitignored `.env` (never committed, logged, cached or put in a URL). Tests use a placeholder.
- `scholar_compare.proceedings_key` was already fixed in milestone A (PR #130): any native id other than a NeurIPS,
  ICLR or PMLR one names no key, so an ojs.aaai.org link falls back to DOI or title matching. Task 1 must read the
  merged code and only extend it where B needs to (AAAI `dblp-`, `doi-`, and the venue-tagged PMLR map). It must not
  re-do it, and must not reintroduce an assert.
- Milestone A as merged differs in places from the branch this plan was drafted against, so read the merged code
  first:
  - `ojs_harvest.py` is split out;
  - `dedup.attribution` has an `ojs` branch;
  - an OJS count mismatch stops the crawl;
  - official-count rows were added;
  - the TASK-218 owner decisions are applied.
  Where task text names line numbers, find the code by name.
- **Correction (Task 8, 2026-10-10): AAAI was not held in 1995 either.** The not-held years are 1981, 1985, 1989,
  1995, 2001, 2003 and 2009, so AAAI 1980–2008 has 23 held years (23 listings, 4,730 records). Where this plan lists six
  years or 24 listings it is superseded; the shipped `dblp_aaai.toml` and spec 01 are as built. FAccT is 1,230 records
  (1,239 ACM DOIs, minus 26 FAccT 2020 not-paper rows, plus 17 from PMLR v81), not the brief's 1,341 + 575.
- e2e runs on `OP_E2E_API_PORT=8100 OP_E2E_WEB_PORT=3100` (the owner's dev servers hold :8000 and :3000).

## Planner decisions (where the spec is silent; for the controller to rule on)

**Records and native ids**
- Planner decision: `[[not_paper]]` entries of the three new sources (dblp AAAI, Crossref, PMLR v81) are **counted, never records**, as the design says. ICML's existing dblp `[[not_paper]]` rows stay records of track `other` (unchanged, out of scope). The two rules differ on purpose; spec 01 will say so.
- Planner decision: the AAAI native id is `dblp-<key after conf/aaai/>`, as the design fixes. A tail can coincide with an ICML tail (`conf/icml/Smith90` and `conf/aaai/Smith90`), so `takedowns.global_native` scopes dblp ids by venue (`aaai:dblp-Smith90`). `urls.native` reads `/rec/conf/aaai/` as well as `/rec/conf/icml/`. The alternative `dblp-aaai-<tail>` was rejected because it breaks the design's form.
- Planner decision: `doi-<toc>.<n>` takes digits only on both sides, for FAccT and AIES.
  - `record.DOI_YEARS` bounds it: AIES 2018–2023 (OJS from 2024) and FAccT 2019 on (PMLR before).
  - `urls.native` maps only `doi.org` / `dx.doi.org` links whose toc is a row of `acm_proceedings.toml`.
  - A DOI that extends a listed toc with any other suffix stops the crawl (`odd_doi`).
  - `doi-` ids are global in `takedowns`.
- Planner decision: a non-ICML `pmlr-` id must name an ingested volume of its own venue and year (record check). ICML's `pmlr-` rule is unchanged.

**dblp layout**
- Planner decision: AAAI's extract is its own file, `<cache>/dblp/extract/aaai/<release sha256>.json`. ICML's `<cache>/dblp/extract/<sha256>.json` keeps its path, format `"1"` and bytes. Reasons:
  - ICML's markers replay that exact file (guarantee 4). Adding AAAI entries to it would change its bytes, and would force a format bump and a rewrite of ICML's extract.
  - Separate files let each venue's table check run alone.
  - Whenever a run has to read the release, one streaming pass writes every slice that is missing (`read_streams`), so the release is still read once.
- Planner decision: the release and DTD pin stays only in `dblp_icml.toml`. `dblp_aaai.toml` holds no `[release]`/`[dtd]`, and its loader takes the pin from `dblp_table.TABLE`, so two pins can never drift apart.
- Planner decision: AAAI markers live in `<cache>/dblp/aaai-crawls/` behind their own `Crawls` (`crawl.DBLP_AAAI`), so ICML's replay never reads an AAAI marker. Both share the `<cache>/dblp` lock.
- Planner decision: the not-held years are data. `dblp_aaai.toml` has `not_held = [1981, 1985, 1989, 2001, 2003, 2009]`.
  - A `conf/aaai/` proceedings key dated to a not-held year stops the ingest.
  - `op ingest dblp --venue AAAI --year 1980-2008` skips not-held years and lists them under `not_held` in its output.
  - A test pins that the shipped table's years plus `not_held` are exactly 1980–2009.

**PMLR**
- Planner decision: a count mismatch stops a **non-ICML** PMLR volume (`count_mismatch`). ICML volumes keep today's warning; tightening them is a separate change.
- Planner decision: the PMLR v81 row is `papers = 20`, keeping the column's meaning (entries on the index), plus a new `not_papers` column holding the three keys. That gives 17 records.
- Planner decision: `urls.native` learns v81 through a new venue-tagged map, `volumes.PMLR_NATIVE_VOLUMES`. Without it a FAccT 2018 record cannot name itself and dedup refuses the snapshot. `ICML_PMLR_VOLUMES`, `icml_volume` and the RIS importer stay ICML-only: a v81 `pmlr_url` in a RIS file is still `out_of_scope`. `scholar_compare.proceedings_key` reads the venue-tagged map.

**Crossref and the FAccT site**
- Planner decision: a Crossref claim's url is the work's API URL (`https://api.crossref.org/works/<doi>`), never a cursor page. `dedup.attribution` credits `crossref` and `facct_site` abstracts to the record's `urls.proceedings` (the DOI link), never an API, CSV or listing URL.
- Planner decision: the Crossref title is the first `title`, plus `": "` and the first `subtitle` when there is one that the title does not already contain. Markup is stripped and entities are unescaped.
  - A work with no title stops the crawl (`no_title`) unless a `[[not_paper]]` row names its DOI.
  - A work with no authors becomes a record with no authors, counted as `no_authors`.
- Planner decision: Crossref abstracts are never read (`select` leaves them out), as the design says.
- Planner decision: a Crossref chain is followed from `cursor=*` through the cache. A live run whose cached chain is incomplete starts again from `cursor=*` with the first page refreshed, because cursors expire after minutes. The total must not move mid-chain (`listing_changed`).
- Planner decision: the FAccT site pages are fetched by `op ingest crossref`, for the FAccT years `facct_site.toml` lists (the `icml_sites` pattern). There is no separate `op ingest facct-site`, and spec 08's `facct-site` crawl target folds into `crossref` (Task 11).
- Planner decision: there is one page per FAccT year, each with `join = "doi"` or `join = "title"`.
  - 2025 joins by DOI. A 2025 row without a DOI is `site_unmatched` and is never joined by title.
  - 2022 and 2026 join by title key.
- Planner decision: the HTTP layer gains `expect="text"` for the CSVs. A 200 is whole when it matches a stated `Content-Length`. When none is stated it is accepted, and the page's verified row count is the guard.
- Planner decision: `CROSSREF_MAILTO` comes from the environment or `.env` and is required for a live Crossref crawl only. It never appears in a URL, a cache entry, a claim or a log line.

**CLI, replay and reporting**
- Planner decision: the new and changed commands are:
  - `op ingest dblp --venue {ICML,AAAI}` (default ICML; `--refresh` is refused for AAAI, since nothing is fetched);
  - `op ingest pmlr --venue {ICML,FAccT}` (default ICML);
  - `op ingest crossref [--venue FAccT|AIES]... [--year Y[-Y]]... [--dry-run|--offline] [--refresh] [--delay S]`.
- Planner decision: `crawl.SOURCES` ends `…, PMLR, DBLP, OJS, DBLP_AAAI, CROSSREF`.
- Planner decision: Task 1 also fixes a latent milestone A bug. `scholar_compare.proceedings_key` reaches an `assert` (an AssertionError, not a ValueError) for an OJS URL in a reviewer's RIS file. It now returns None for `ojs-`, AAAI `dblp-` and any other native whose URL carries no year.
- Planner decision: `coverage_report._scope` splits dblp listings by venue. Today it would print "ICML 1980–2012".
- Planner decision: Crossref's date window is chosen by the census (Task 9): the toc DOIs' earliest and latest `published` dates, padded by 7 days. It is confirmed by an independent route, Crossref's `isbn:` filter count for the proceedings' ISBN, and recorded in the research note.
- Planner decision: AIES ACM entries are all `main`, as the design says. The census lists entries of two pages or fewer for owner review without remapping them.
- Planner decision: no `official_counts.py` row is added unless the census finds an independent accepted count (milestone A's rule). The ACM tables of contents and the PMLR index are the sources themselves.

## Global Constraints

**Schema and vocabulary**
- `RECORD_SCHEMA_VERSION` `"6"` → `"7"` (new claim sources `crossref` and `facct_site`; the `doi-` native form; `dblp-` widened to AAAI; `pmlr-` widened to FAccT). The index `SCHEMA_VERSION` stays `"3"`.
- No vocabulary change: no venue, track or `CONFERENCES` row is added. The synthetic 5k corpus (`backend/tests/fixtures/corpus/synthetic_5k.py`) stays pinned to its 3 venues and 9 tracks and is never reshuffled. Tests that enumerate venues read `vocab.VENUES`; tests that enumerate the corpus read its pinned tuples.
- Native forms:
  - `doi-<toc>.<n>`: FAccT 2019+, AIES 2018–2023 (`record.DOI_YEARS`);
  - `dblp-<key>`: ICML 1988–2012 and AAAI 1980–2008 (`record.DBLP_YEARS` becomes a per-venue `Mapping[str, range]`);
  - `pmlr-v81-<key>`: FAccT 2018.
- Every record is `accepted`. Track is `main`, except the papers under a dblp AAAI `[[workshop]]` key, which are `workshop`.

**What stays untouched**
- ICML: the dblp extract's path, format and bytes; `dblp_icml.toml`; `ICML_PMLR_VOLUMES`; `icml_volume`; the RIS importer; ICML's count-mismatch behaviour.
- dblp's AAAI keys dated 2010 or later are never read (OJS owns those years), and neither are `conf/iaai/` or `conf/eaai/`.

**Hosts and politeness**
- New hosts: `api.crossref.org` (sequential, at least 1 s apart, `mailto` in the User-Agent) and `facctconference.org` (at least 1 s).
- Existing hosts: `proceedings.mlr.press`; `drops.dagstuhl.de` (no new download).
- Never fetched: `dl.acm.org`, `dblp.org` or `aaai.org`.

**Stops**
- A count that differs from a table's verified count stops the crawl (`count_mismatch`).
- So do a table unit absent from the source (`table_mismatch`, `stale_not_paper`) and an unlisted unit (`unlisted_proceedings`).
- A crawl is never a silently shorter harvest.

**Tests and fixtures**
- No test reaches the network (`backend/tests/conftest.py`).
- Recorded fixtures are scrubbed (decision-004): real ids, DOIs, keys, cursors and counts; synthetic titles, authors and abstracts.
- Every task that touches records, sources, dedup, urls or takedowns runs the full backend suite: `uv run pytest backend/tests -q -n auto`.

**Process**
- Commits and PRs carry no AI attribution (hook `block-ai-attribution.sh`).
- Work on `feat/new-venues-b`, cut from `dev` after milestone A merges, in its own worktree.
- Logging: structured JSON, one line per unit of work. Never abstracts, query text, credentials or the Crossref contact address.
- Docs, specs and backlog are updated in the same commit as the change they describe. The backlog is edited only through the `backlog` CLI.
- Out of scope: IASEAI 2027 (OpenReview; no public papers until 2026-11-20), AIES 2026 (an OJS table row once published), OpenAlex and `abstract_kind`.

## Review Focus

1. **A Crossref cursor that changes between runs.** Crossref cursors expire after minutes, so a resumed crawl's cached chain points at a dead cursor.
   - A person expects the run to start the chain again from `cursor=*` and never to send a stale cursor or keep half a chain.
   - A person expects the snapshot build to follow exactly the chain the cache holds.
   - Pinned by Task 7: `test_a_resumed_crawl_whose_chain_is_not_whole_starts_again_from_cursor_star`, `test_the_replay_follows_the_cached_chain_offline`, `test_a_total_that_moves_mid_chain_stops`.
2. **A DOI with odd characters.** Examples: `10.1145/3593013.3594011a`, a `%0A`, a toc DOI with no paper suffix, a foreign toc.
   - A person expects no record id built from it.
   - A person expects a stop that names the DOI, never a skipped and miscounted paper.
   - Pinned by Task 6 (`test_a_link_that_is_not_a_listed_acm_paper_names_nothing`, `test_malformed_doi_native_id_is_refused`) and Task 7 (`test_an_odd_doi_under_the_proceedings_stops`).
3. **Title-key collisions in the 2026 CSV.** Two rows whose titles differ only in case or punctuation, or one title shared by two papers.
   - A person expects neither abstract attached, both rows counted `site_ambiguous`, and never a guessed join.
   - Pinned by Task 10: `test_two_rows_sharing_a_title_key_attach_nothing`, `test_two_records_sharing_a_title_key_attach_nothing`.
4. **dblp homonym numbers in AAAI author names.** dblp writes `Wei Wang 0001`.
   - A person expects `Wei Wang`, and any other trailing token kept as written.
   - Pinned by Task 4: `test_aaai_records_from_the_release` (author assertions) and `test_clean_author_drops_only_a_four_digit_homonym`.
5. **A Crossref record with no title or no authors.**
   - With no title, a person expects a stop naming the DOI (add a `[[not_paper]]` row or check Crossref), never a nameless record.
   - With no authors, a person expects the paper kept with no authors and counted.
   - Pinned by Task 7: `test_a_work_with_no_title_stops_unless_a_not_paper_row_names_it`, `test_a_work_with_no_authors_is_kept_and_counted`.

---

## File map

| File | Responsibility | Task |
|---|---|---|
| `backend/src/openproceedings/ingest/record.py` | schema 7; `Source`; `doi` form; per-venue `DBLP_YEARS`; `DOI_YEARS`; non-ICML `pmlr-` check | 1, 5 |
| `ingest/statuses.py`, `ingest/dedup.py`, `export.py`, `api/models.py`, `frontend/src/components/search/hit-item.tsx` | the two sources' statuses, precedence, origins, attribution, display names | 1 |
| `backend/src/openproceedings/takedowns.py` | `doi-` global; dblp scoped by venue | 1 |
| `backend/src/openproceedings/eval/scholar_compare.py` | `proceedings_key` without the assert; later the venue-tagged PMLR and DOI keys | 1, 5, 6 |
| `ingest/dblp_table.py` | ICML bounds from `DBLP_YEARS["ICML"]` | 1 |
| `ingest/sources/http.py` | `Fetcher(user_agent=…)`; `expect="text"` | 2 |
| `ingest/sources/dblp_xml.py` | `read_streams` (several prefixes, one pass) | 3 |
| `ingest/sources/dblp.py` | `Slice`, `ICML_SLICE`/`AAAI_SLICE`, `write_extracts`, `prepare_slices`; `links(pdf_hosts=…)` | 3, 4 |
| `ingest/dblp_aaai_table.py` + `ingest/dblp_aaai.toml` | the AAAI key table | 3 (loader), 8 (rows) |
| `ingest/sources/dblp_aaai.py` | AAAI check, records, reports | 4 |
| `ingest/urls.py` | `dblp_aaai`, the v81 rule, `acm_doi`, `native()` | 4, 5, 6 |
| `ingest/volumes.py` + `pmlr_volumes.toml`, `ingest/sources/pmlr.py` | FAccT allowlist, `not_papers`, `PMLR_NATIVE_VOLUMES`, `ingested_volume` | 5 (code), 9 (row) |
| `ingest/acm_table.py` + `ingest/acm_proceedings.toml` | ACM proceedings, windows, counts, not-paper DOIs | 6 (loader), 9 (rows) |
| `ingest/sources/crossref.py` | Crossref parse, chain, records, report | 6, 7, 10 |
| `ingest/facct_site.toml` + `ingest/sources/facct_site.py` | FAccT pages, parsers, joins | 10 |
| `ingest/sources/crawl.py`, `cli.py` | `ingest_dblp_aaai`, `ingest_pmlr(venue=)`, `ingest_crossref`, `DBLP_AAAI`, `CROSSREF`, `SOURCES` | 4, 5, 7, 10 |
| `eval/coverage_report.py` | `_scope` by venue | 4 |
| `backend/tests/fixtures/http/scrub.py` | Crossref JSON and CSV scrubbing branches | 9 |
| `backend/tests/fixtures/http/{crossref,facct_site,pmlr/v81}/…` | recorded, scrubbed pages | 9 |
| `scripts/dblp_aaai_census.py`, `scripts/acm_census.py` | read-only census helpers | 8, 9 |
| `docs/research/2026-10-09-aaai-aies-facct-iaseai-sources.md` | the census facts | 8, 9 |
| specs 00/01/04/05/07/08, README, CLAUDE.md, design status, decision-049, skills, `.env.example`, cspell | docs as built | 11 |

---

### Task 1: Record model: two sources, `doi-` ids, AAAI `dblp-` ids, schema 7

**Files:**
- Modify: `backend/src/openproceedings/ingest/record.py:41-81, 338-356` (schema comment and constant, `Source`, `PROCEEDINGS_NATIVE`, `DBLP_YEARS`, new `DOI_YEARS`, `_consistent`)
- Modify: `backend/src/openproceedings/ingest/dblp_table.py:29-36` (`FIRST_YEAR`, `LAST_YEAR` from `DBLP_YEARS["ICML"]`)
- Modify: `backend/src/openproceedings/ingest/statuses.py:33-46`
- Modify: `backend/src/openproceedings/ingest/dedup.py:76-81` (`_TEXT`, `_ACCEPTANCE`), `:220-230` (`Origin`, `_DIRECT_ORIGIN`), `:318-324` (`attribution`)
- Modify: `backend/src/openproceedings/export.py:97-105`, `frontend/src/components/search/hit-item.tsx:105-113`, `backend/src/openproceedings/api/models.py:158-164` (`ORIGIN_DOC`)
- Modify: `backend/src/openproceedings/takedowns.py:106-122` (`_LOCAL_NATIVE`, `global_native`)
- Modify: `backend/src/openproceedings/eval/scholar_compare.py:195-206` (`proceedings_key`)
- Modify tests: `backend/tests/unit/ingest/test_record.py`, `test_dedup.py:163-177`, `backend/tests/unit/test_takedowns.py:280-287`, `backend/tests/unit/test_scholar_compare.py`, `backend/tests/unit/test_export.py:231-234`

**Interfaces:**
- Produces:
  - `record.Source` adds `"crossref"` and `"facct_site"` (before `"ris"`).
  - `record.PROCEEDINGS_NATIVE["doi"] == (re.compile(r"doi-[0-9]+\.[0-9]+"), frozenset({"AIES", "FAccT"}))`; `PROCEEDINGS_NATIVE["dblp"][1] == frozenset({"AAAI", "ICML"})`.
  - `record.DBLP_YEARS: Mapping[str, range] = {"ICML": range(1988, 2013), "AAAI": range(1980, 2009)}`.
  - `record.DOI_YEARS: Mapping[str, range] = {"AIES": range(2018, 2024), "FAccT": range(2019, 10000)}`.
  - `dedup.Origin` adds `"crossref"` and `"facct_site"`.
  - `export.ORIGIN_NAMES["crossref"] == "Crossref"`; `export.ORIGIN_NAMES["facct_site"] == "FAccT conference site"`.
  - `takedowns.global_native("op:aaai:1990:dblp-X") == "aaai:dblp-X"`.

- [ ] **Step 1: Write the failing tests** (append to `test_record.py`)

```python
from openproceedings.ingest.record import DBLP_YEARS, DOI_YEARS, RECORD_SCHEMA_VERSION


def _rec(rid: str, venue: str, year: int, track: str = "main") -> PaperRecord:
    return PaperRecord.build(id=rid, title="A paper", abstract=None, authors=("A. Author",), venue=venue,
                             year=year, track=track, status="accepted")  # fmt: skip


def test_schema_is_7() -> None:
    assert RECORD_SCHEMA_VERSION == "7"


@pytest.mark.parametrize(("venue", "year"), [("FAccT", 2019), ("FAccT", 2026), ("AIES", 2018), ("AIES", 2023)])
def test_doi_native_id_is_valid_for_the_acm_venue_years(venue: str, year: int) -> None:
    r = _rec(f"op:{venue.lower()}:{year}:doi-3593013.3594011", venue, year)
    assert r.native == "doi-3593013.3594011" and r.forum_id is None


@pytest.mark.parametrize(("venue", "year"), [("ICML", 2023), ("AAAI", 2023), ("AIES", 2024), ("FAccT", 2018)])
def test_doi_native_id_is_refused_outside_its_venue_years(venue: str, year: int) -> None:
    with pytest.raises(ValidationError, match="not a valid"):
        _rec(f"op:{venue.lower()}:{year}:doi-3593013.3594011", venue, year)


@pytest.mark.parametrize(
    "native", ["doi-", "doi-3593013", "doi-3593013.", "doi-3593013.3594011a", "doi-3593013.359.4011", "doi-x.1"]
)
def test_malformed_doi_native_id_is_refused(native: str) -> None:
    with pytest.raises(ValidationError):
        _rec(f"op:facct:2023:{native}", "FAccT", 2023)


@pytest.mark.parametrize(
    ("venue", "year", "ok"),
    [("AAAI", 1980, True), ("AAAI", 2008, True), ("AAAI", 2009, False), ("AAAI", 2010, False),
     ("ICML", 1988, True), ("ICML", 2012, True), ("ICML", 2013, False)],
)  # fmt: skip
def test_dblp_ids_are_icml_1988_2012_and_aaai_1980_2008(venue: str, year: int, ok: bool) -> None:
    rid = f"op:{venue.lower()}:{year}:dblp-Smith90"
    if ok:
        assert _rec(rid, venue, year).native == "dblp-Smith90"
    else:
        with pytest.raises(ValidationError, match="dblp ids are"):
            _rec(rid, venue, year)


def test_dblp_ids_are_refused_for_another_venue() -> None:
    with pytest.raises(ValidationError, match="not a valid"):
        _rec("op:aies:2018:dblp-Smith18", "AIES", 2018)


def test_the_year_tables_name_their_venues() -> None:
    assert set(DBLP_YEARS) == {"ICML", "AAAI"} and set(DOI_YEARS) == {"AIES", "FAccT"}
```

Append to `test_dedup.py`. Update `test_the_precedence_table_is_decision_005`'s `text` to end `"ojs", "crossref", "facct_site", "ris"`, and its status tuple to insert `"crossref"` after `"ojs"`. Then add:

```python
@pytest.mark.parametrize(
    ("source", "url"),
    [("crossref", "https://api.crossref.org/works/10.1145/3593013.3594011"),
     ("facct_site", "https://facctconference.org/static/docs/facct2025-final.csv")],
)  # fmt: skip
def test_an_acm_abstract_is_credited_to_the_doi_link_never_an_api_or_listing_url(source: str, url: str) -> None:
    doi = "https://doi.org/10.1145/3593013.3594011"
    got = attribution("T", [_abstract(source, "T", url)], forum=None, proceedings=doi, native="doi-3593013.3594011")
    assert got == Attribution(source, source, doi)
```

In `test_takedowns.py`, add rows to `test_only_globally_unique_native_ids_link`: `("op:facct:2023:doi-3593013.3594011", True)` and `("op:aaai:1990:dblp-Smith90", True)`. Then add:

```python
def test_a_dblp_key_links_only_within_its_venue() -> None:
    """AAAI and ICML dblp tails can coincide (`conf/aaai/Smith90`, `conf/icml/Smith90`): one paper's takedown
    never hides the other venue's paper, and still follows its own record to another year."""
    held = ["op:aaai:1990:dblp-Smith90", "op:icml:1991:dblp-Smith90"]
    assert takedowns.same_paper(frozenset({"op:icml:1990:dblp-Smith90"}), (), held) == {"op:icml:1991:dblp-Smith90"}
```

In `test_scholar_compare.py`:

```python
def test_an_ojs_article_page_names_no_proceedings_key() -> None:  # no year in the URL; never an AssertionError
    assert proceedings_key("https://ojs.aaai.org/index.php/AAAI/article/view/28000") is None
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest backend/tests/unit/ingest/test_record.py backend/tests/unit/ingest/test_dedup.py backend/tests/unit/test_takedowns.py backend/tests/unit/test_scholar_compare.py -q -n auto`

Expected: FAIL. Schema is `"6"`; `doi-…` is "neither an OpenReview forum id nor a proceedings id"; the precedence tuples differ; `proceedings_key` raises `AssertionError`.

- [ ] **Step 3: Implement**

In `record.py`:

```python
# 7: the `crossref` and `facct_site` sources, the `doi-<toc>.<n>` native id (FAccT, AIES), `dblp-` ids for AAAI
# 1980-2008 and `pmlr-` ids for FAccT 2018 (decision-049, milestone B); 6: the AAAI, AIES, FAccT and IASEAI venues,
# five tracks, the `ojs` source and the `ojs-<article id>` native id (decision-049); 5: …
RECORD_SCHEMA_VERSION = "7"
...
Source = Literal[
    "openreview_v2", "openreview_v1", "iclr_archive", "neurips_proceedings", "pmlr", "dblp", "icml_site", "ojs",
    "crossref", "facct_site", "ris",
]  # fmt: skip
...
    # the dblp key after `conf/icml/` (ICML 1988-2012) or `conf/aaai/` (AAAI 1980-2008) (sources/dblp*.py)
    "dblp": (re.compile(r"dblp-[A-Za-z0-9_-]+"), frozenset({"ICML", "AAAI"})),
    ...
    # an ACM paper DOI's suffix, `10.1145/<toc>.<n>` → `doi-<toc>.<n>` (FAccT, AIES; sources/crossref.py)
    "doi": (re.compile(r"doi-[0-9]+\.[0-9]+"), frozenset({"FAccT", "AIES"})),
}
# the years a `dblp-` id may name, per venue: ICML before PMLR (v28, 2013); AAAI before OJS (Vol. 24, 2010)
DBLP_YEARS: Mapping[str, range] = MappingProxyType({"ICML": range(1988, 2013), "AAAI": range(1980, 2009)})
# the years a `doi-` id may name: AIES before OJS (Vol. 7, 2024); FAccT after PMLR v81 (2018)
DOI_YEARS: Mapping[str, range] = MappingProxyType({"AIES": range(2018, 2024), "FAccT": range(2019, 10000)})
```

In `_consistent`, replace the dblp year check with:

```python
            if native.startswith("dblp-") and self.year not in DBLP_YEARS[self.venue]:
                raise ValueError(
                    f"native id {native!r} is not a valid id for {self.venue} {self.year}: dblp ids are ICML "
                    "1988-2012 and AAAI 1980-2008"
                )
            if native.startswith("doi-") and self.year not in DOI_YEARS[self.venue]:
                raise ValueError(
                    f"native id {native!r} is not a valid id for {self.venue} {self.year}: doi ids are AIES "
                    "2018-2023 and FAccT 2019 on"
                )
```

(The message starts "not a valid", so the venue-year tests match.)

In `dblp_table.py`: `FIRST_YEAR, LAST_YEAR = DBLP_YEARS["ICML"][0], DBLP_YEARS["ICML"][-1]`. In `test_export.py:234`: `"ICML": DBLP_YEARS["ICML"][0]`.

In `statuses.py`, add:

```python
    # FAccT 2019+ and AIES 2018-2023 from Crossref's ACM proceedings records, and the official FAccT pages'
    # abstracts of some of them: published papers only (decision-049, milestone B)
    "crossref": (ACCEPTED_ONLY, ACCEPTED_ONLY),
    "facct_site": (ACCEPTED_ONLY, ACCEPTED_ONLY),
```

In `dedup.py`:
- `_TEXT` becomes `(…, "ojs", "crossref", "facct_site", "ris")`.
- `_ACCEPTANCE` becomes `(…, "dblp", "ojs", "crossref", "openreview_v2", …)`. `facct_site` claims only abstracts, so it is not in `_ACCEPTANCE`, as `icml_site` isn't.
- Add `crossref` beside the dblp/ojs comment on `PROCEEDINGS_SOURCES` ("not one either: no other source holds its venue-years").
- `Origin` adds `"crossref", "facct_site"`. `_DIRECT_ORIGIN` adds `"crossref": "crossref"` and `"facct_site": "facct_site"`.
- In `attribution`, widen the `ojs` branch:

```python
    if origin in ("ojs", "crossref", "facct_site"):
        # each claim's url is an API page (an OAI token page, a Crossref work), or a listing of every paper (a FAccT
        # CSV): credit the paper's own page, its urls.proceedings (the article page, the DOI link)
        return Attribution(source, origin, proceedings)
```

In `export.py` `ORIGIN_NAMES` and in `hit-item.tsx` `ORIGIN_NAMES`, add `crossref: "Crossref"` and `facct_site: "FAccT conference site"`. In `ORIGIN_DOC`, add: "`crossref` and `facct_site`: FAccT and AIES (ACM proceedings via Crossref, the official FAccT pages); the url is the paper's DOI link (decision-049)."

In `takedowns.py`:

```python
_LOCAL_NATIVE = tuple(
    f"{prefix}-" for prefix in PROCEEDINGS_NATIVE if prefix not in ("pmlr", "dblp", "ojs", "doi")
)


def global_native(rid: str) -> str | None:
    """… (docstring as now, plus:) A DOI is unique everywhere. A dblp key is unique within its venue's `conf/<venue>/`
    stream only (an ICML and an AAAI tail can coincide), so a dblp id is scoped by its venue (`aaai:dblp-<key>`)."""
    venue, native = rid.split(":", 3)[1], rid.split(":", 3)[-1]
    if native.startswith(_LOCAL_NATIVE):
        return None
    return f"{venue}:{native}" if native.startswith("dblp-") else native
```

In `scholar_compare.proceedings_key`:

```python
    native = urls.native(url)
    if native is None or not native.startswith(("nips-", "iclr-", "pmlr-")):
        return None  # a dblp page, an ojs article page: the URL carries no year (a `doi-` key arrives in Task 6)
    if (parts := urls.proceedings_parts(url)) is not None:
        return (parts[0], parts[1], native)
    volume = urls.pmlr(url)
    if volume is None or volume[0] not in ICML_PMLR_VOLUMES:
        return None
    return ("ICML", ICML_PMLR_VOLUMES[volume[0]][0], native)
```

Update its docstring.

- [ ] **Step 4: Run the full backend suite and regenerate the contract**

Run: `uv run pytest backend/tests -q -n auto`. Expected: PASS, apart from staleness tests naming `openapi.json` (the `Source`/`Origin` literals).

Run `make openapi`, then re-run `uv run pytest backend/tests/contract -q -n auto` and `npm test --workspace frontend`. Expected: PASS.

Fix any test that pinned `RECORD_SCHEMA_VERSION == "6"` or `PROCEEDINGS_NATIVE["dblp"][1] == frozenset({"ICML"})` (`grep -rn '"6"\|frozenset({"ICML"})' backend/tests`).

- [ ] **Step 5: Commit**

```bash
git add -A backend frontend
git commit -m "feat: crossref and facct_site claim sources, doi-<toc>.<n> ids for FAccT and AIES, dblp ids for AAAI 1980-2008; record schema 7 (decision-049)"
```

---

### Task 2: HTTP layer: a source's own User-Agent and plain-text responses

**Files:**
- Modify: `backend/src/openproceedings/ingest/sources/http.py:272-279` (`Policy.expect`), `:455-480` (`_truncated`), `:614-658` (`Fetcher.__init__`, `_page`), and the module docstring's truncation bullet
- Test: `backend/tests/unit/ingest/test_http.py` (append)

**Interfaces:**
- Produces: `Policy.expect: Literal["html", "json", "xml", "text"]`, and:

```python
Fetcher(cache, transport, *, hosts, min_interval=1.0, attempts=5, max_wait=3600.0, timeout=30.0,
        clock=None, accept="text/html", expect="html", keep_query=False, user_agent: str | None = None)
```

  - `user_agent` replaces `USER_AGENT` on every request. It never reaches the cache or a log line.
  - With `expect="text"`, a 200 is truncated only when it states a `Content-Length` its body does not match.

- [ ] **Step 1: Write the failing tests**

```python
CROSSREF = "https://api.crossref.org/works/10.1145/3593013"
JSON = {"content-type": "application/json"}


def test_a_fetcher_sends_its_own_user_agent_and_never_stores_it(tmp_path: Path) -> None:
    sent: list[dict[str, str]] = []

    def transport(request: Request, timeout: float) -> Response:
        sent.append(dict(request.headers))
        return response('{"status": "ok"}', headers=JSON)

    ua = "openproceedings/test (mailto:reviewer@example.org)"
    f, _ = fetcher(tmp_path, transport, frozenset({"api.crossref.org"}), min_interval=0.0, accept="application/json",
                   expect="json", user_agent=ua)  # fmt: skip
    assert f.get(CROSSREF).ok
    assert sent[0]["User-Agent"] == ua
    assert all("reviewer@example.org" not in p.read_text() for p in tmp_path.rglob("*.json"))


def test_the_default_user_agent_is_unchanged(tmp_path: Path) -> None:
    sent: list[dict[str, str]] = []

    def transport(request: Request, timeout: float) -> Response:
        sent.append(dict(request.headers))
        return response("<html></html>")

    f, _ = fetcher(tmp_path, transport, frozenset({"proceedings.mlr.press"}), min_interval=0.0)
    f.get("https://proceedings.mlr.press/v81/")
    assert sent[0]["User-Agent"] == USER_AGENT


CSV_URL = "https://facctconference.org/static/docs/facct2026-final.csv"


@pytest.mark.parametrize(
    ("headers", "whole"),
    [({"content-type": "text/csv"}, True), ({"content-type": "text/csv", "content-length": "9"}, True),
     ({"content-type": "text/csv", "content-length": "99"}, False)],
)  # fmt: skip
def test_a_text_page_is_judged_by_its_stated_length(tmp_path: Path, headers: dict[str, str], whole: bool) -> None:
    t = FakeTransport({CSV_URL: response("a,b\n1,2\n\n", headers=headers)})  # 9 bytes
    f, _ = fetcher(tmp_path, t, frozenset({"facctconference.org"}), min_interval=0.0, attempts=2,
                   accept="text/csv", expect="text")  # fmt: skip
    if whole:
        assert f.get(CSV_URL).text.startswith("a,b")
    else:
        with pytest.raises(RetriesExhausted):
            f.get(CSV_URL)
```

Import `Request`, `Response` and `USER_AGENT` from `http.py` if the file does not already. If `fetcher` refuses a plain function as its transport type, wrap the function in a one-entry `FakeTransport`-style class.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest backend/tests/unit/ingest/test_http.py -q -k "user_agent or text_page"`

Expected: FAIL (`TypeError: … unexpected keyword argument 'user_agent'`).

- [ ] **Step 3: Implement**

- `Policy.expect: Literal["html", "json", "xml", "text"] = "html"`.
- In `_truncated`, after the `by_length` branch and before the html branch:

```python
        if self.policy.expect == "text":
            # a CSV has no closing tag: whole unless it states a length it doesn't have (the source's own row count
            # is the guard when none is stated: facct_site checks each page's verified count)
            if stated.isascii() and stated.isdecimal() and len(stated) <= 19:
                return "truncated" if int(stated) != len(response.body) else None
            return None
```

- `Fetcher.__init__` gains `user_agent: str | None = None`, stored as `self.user_agent = user_agent or USER_AGENT`. `_page` builds `Request("GET", url, {"User-Agent": self.user_agent, "Accept": self.policy.accept})`.
- Add the `expect` value "text" to every `Literal["html", "json", "xml"]` in the module.
- Docstring: "(… an XML document not ending in its root's closing tag, a text page shorter or longer than its stated `Content-Length`, or JSON that doesn't parse …)".

- [ ] **Step 4: Run and commit**

Run: `uv run pytest backend/tests/unit/ingest/test_http.py backend/tests/unit/ingest/test_fetch.py -q`. Expected: PASS.

```bash
git add backend/src/openproceedings/ingest/sources/http.py backend/tests/unit/ingest/test_http.py
git commit -m "feat: a fetcher sends its source's own User-Agent; plain-text pages judged by their stated length"
```

---

### Task 3: dblp: several streams in one pass, AAAI's own extract, the AAAI table loader

**Files:**
- Modify: `backend/src/openproceedings/ingest/sources/dblp_xml.py:63-66` (`_start_tag`), `:87-125` (`_records`), `:191-202` (`read_streams`, `read_stream`), module docstring
- Modify: `backend/src/openproceedings/ingest/sources/dblp.py:86-196` (`Slice`, `extract_path`, `write_extracts`, `write_extract`, `load_extract`, `prepare_slices`, `prepare`), module docstring
- Create: `backend/src/openproceedings/ingest/dblp_aaai_table.py`, `backend/src/openproceedings/ingest/dblp_aaai.toml` (header and `not_held` only; rows arrive in Task 8)
- Create: `backend/tests/unit/ingest/test_dblp_slices.py`, `backend/tests/unit/ingest/test_dblp_aaai_table.py`

**Interfaces:**
- Produces:
  - `dblp_xml.read_streams(path, dtd, dtd_name, prefixes: tuple[str, ...], progress=None) -> dict[str, list[DblpEntry]]`;
  - `dblp.Slice(venue, prefix, subdir)` with `.path(cache, table=TABLE)`;
  - `dblp.ICML_SLICE`, `dblp.AAAI_SLICE`, `dblp.SLICES`;
  - `dblp.write_extracts(cache, release, dtd, table=TABLE, slices=(ICML_SLICE,)) -> dict[str, Extract]`;
  - `dblp.load_extract(cache, table=TABLE, slice_=ICML_SLICE)`;
  - `dblp.prepare_slices(cache, stream, table=TABLE, slices=SLICES) -> dict[str, Extract]` (no table check);
  - `dblp_aaai_table.{AaaiYear, Workshop, Excluded, NotPaper, Table, load, TABLE, CHECKED, FIRST_YEAR, LAST_YEAR}`;
  - `Table.main_key(crossref)`, `Table.workshop(crossref)`, `Table.stated(year)`.
- Unchanged: `read_stream`, `extract_path`, `write_extract`, `prepare` and `check_extract` keep their signatures and results.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/unit/ingest/test_dblp_slices.py
"""One read of the pinned release writes each venue's slice (decision-049, milestone B); ICML's extract keeps its path
and its bytes (guarantee 4). Synthetic records in the release's framing (decision-004)."""

from __future__ import annotations

import gzip
import hashlib
from pathlib import Path

import pytest
from openproceedings.ingest import dblp_table
from openproceedings.ingest.sources import dblp
from openproceedings.ingest.sources.dblp_xml import DblpFormatError, read_stream, read_streams

from tests.unit.ingest import test_dblp
from tests.unit.ingest.test_dblp_xml import BODY, DTD, DTD_NAME, HEAD, Stream, release

AAAI_BODY = """<inproceedings mdate="2020-01-01" key="conf/aaai/Synthetic86a">
<author>Synthetic Author 1 0001</author>
<author>Synth&uuml;tic Author 2</author>
<title>Synthetic AAAI title 1.</title>
<year>1986</year>
<ee>https://doi.org/10.5555/synthetic.1</ee>
<crossref>conf/aaai/1986-1</crossref>
</inproceedings><inproceedings mdate="2020-01-01" key="conf/aaai/Synthetic86b"><author>Synthetic Author 3</author><title>Synthetic AAAI title 2?</title><year>1986</year><crossref>conf/aaai/1986-2</crossref></inproceedings>
<inproceedings mdate="2020-01-01" key="conf/aaai/Invited86"><author>Synthetic Author 4</author><title>Synthetic invited talk.</title><year>1986</year><crossref>conf/aaai/1986-1</crossref></inproceedings>
<inproceedings mdate="2020-01-01" key="conf/aaai/Withdrawn86" publtype="withdrawn"><author>Synthetic Author 5</author><title>Synthetic title 3.</title><year>1986</year><crossref>conf/aaai/1986-2</crossref></inproceedings>
<proceedings mdate="2020-01-01" key="conf/aaai/1986-1"><title>Synthetic AAAI 1986, Volume 1</title><year>1986</year></proceedings>
<proceedings mdate="2020-01-01" key="conf/aaai/1986-2"><title>Synthetic AAAI 1986, Volume 2</title><year>1986</year></proceedings>
<proceedings mdate="2020-01-01" key="conf/aaai/2006"><title>Synthetic AAAI 2006</title><year>2006</year></proceedings>
<inproceedings mdate="2020-01-01" key="conf/aaai/Main06"><author>Synthetic Author 7</author><title>Synthetic main paper.</title><year>2006</year><crossref>conf/aaai/2006</crossref></inproceedings>
<proceedings mdate="2020-01-01" key="conf/aaai/2006w"><title>Synthetic AAAI 2006 workshop</title><year>2006</year></proceedings>
<inproceedings mdate="2020-01-01" key="conf/aaai/Workshop06"><author>Synthetic Author 6</author><title>Synthetic workshop paper.</title><year>2006</year><crossref>conf/aaai/2006w</crossref></inproceedings>
<proceedings mdate="2020-01-01" key="conf/aaai/2024"><title>Synthetic AAAI 2024</title><year>2024</year></proceedings>
<inproceedings mdate="2020-01-01" key="conf/aaai/Late24"><author>Synthetic Author 8</author><title>Never read.</title><year>2024</year><crossref>conf/aaai/2024</crossref></inproceedings>
"""
FULL = BODY.replace("</dblp>\n", "") + AAAI_BODY + "</dblp>\n"
GZ_FULL = gzip.compress((HEAD + FULL).encode("latin-1"), mtime=0)


def pins(gz: bytes) -> dblp_table.Table:
    """test_dblp's ICML table, pinned to `gz` instead of its own release."""
    text = test_dblp.table_text(sha=hashlib.sha256(gz).hexdigest())
    return dblp_table.load(text.replace(f"size = {len(test_dblp.GZ)}", f"size = {len(gz)}", 1))


def on_disk(tmp_path: Path, gz: bytes = GZ_FULL) -> tuple[dblp_table.Table, object, object]:
    table = pins(gz)
    release, dtd = dblp.fetch_release(tmp_path, Stream((200, DTD), (200, gz)), table)
    return table, release, dtd


def test_read_streams_splits_one_pass_by_prefix(tmp_path: Path) -> None:
    path = release(tmp_path, FULL)
    both = read_streams(path, DTD, DTD_NAME, ("conf/icml/", "conf/aaai/"))
    assert [e.key for e in both["conf/icml/"]] == [e.key for e in read_stream(path, DTD, DTD_NAME, "conf/icml/")]
    assert {e.key for e in both["conf/aaai/"]} >= {"conf/aaai/Synthetic86a", "conf/aaai/1986-1", "conf/aaai/Late24"}
    assert all(e.key.startswith("conf/aaai/") for e in both["conf/aaai/"])


@pytest.mark.parametrize("prefixes", [("conf/icml/", "conf/icml/"), ("conf/", "conf/aaai/")])
def test_overlapping_prefixes_are_refused(tmp_path: Path, prefixes: tuple[str, ...]) -> None:
    with pytest.raises(ValueError, match="distinct"):
        read_streams(release(tmp_path, FULL), DTD, DTD_NAME, prefixes)


def test_an_aaai_key_outside_a_record_start_tag_is_refused(tmp_path: Path) -> None:
    body = FULL.replace("</dblp>", '<www key="x"><note>key="conf/aaai/Stray"</note></www></dblp>')
    with pytest.raises(DblpFormatError, match="conf/aaai/"):
        read_streams(release(tmp_path, body), DTD, DTD_NAME, ("conf/icml/", "conf/aaai/"))


def test_the_icml_extract_is_the_same_bytes_whether_or_not_aaai_shares_the_pass(tmp_path: Path) -> None:
    table, rel, dtd = on_disk(tmp_path)
    alone = dblp.write_extract(tmp_path, rel, dtd, table)
    first = dblp.extract_path(tmp_path, table).read_bytes()
    both = dblp.write_extracts(tmp_path, rel, dtd, table, dblp.SLICES)
    assert dblp.extract_path(tmp_path, table).read_bytes() == first and both["ICML"] == alone
    assert dblp.extract_path(tmp_path, table) == tmp_path / "dblp" / "extract" / f"{table.release.file.sha256}.json"
    assert dblp.AAAI_SLICE.path(tmp_path, table) == tmp_path / "dblp" / "extract" / "aaai" / f"{table.release.file.sha256}.json"
    assert dblp.load_extract(tmp_path, table, dblp.AAAI_SLICE) == both["AAAI"]


def test_prepare_slices_reads_the_release_once_for_every_missing_slice(tmp_path: Path, monkeypatch) -> None:
    table, rel, dtd = on_disk(tmp_path)
    reads: list[tuple[str, ...]] = []
    real = dblp.read_streams
    monkeypatch.setattr(dblp, "read_streams", lambda *a, **k: reads.append(a[3]) or real(*a, **k))
    out = dblp.prepare_slices(tmp_path, None, table, (dblp.AAAI_SLICE,))
    assert reads == [("conf/aaai/", "conf/icml/")] or reads == [("conf/icml/", "conf/aaai/")]  # one read, both
    assert set(out) == {"AAAI"} and dblp.extract_path(tmp_path, table).exists()
    dblp.prepare_slices(tmp_path, None, table, dblp.SLICES)
    assert len(reads) == 1  # both on disk: nothing is read again


def test_an_aaai_extract_holding_another_streams_entry_is_refused(tmp_path: Path) -> None:
    table, rel, dtd = on_disk(tmp_path)
    dblp.write_extracts(tmp_path, rel, dtd, table, dblp.SLICES)
    path = dblp.AAAI_SLICE.path(tmp_path, table)
    path.write_text(path.read_text().replace('"conf/aaai/Main06"', '"conf/icml/Main06"'))
    with pytest.raises(dblp.CrawlError, match="malformed"):
        dblp.load_extract(tmp_path, table, dblp.AAAI_SLICE)
```

(Use `dblp.read_streams` through the module so the monkeypatch sees it: `dblp.py` does `from openproceedings.ingest.sources import dblp_xml` and calls `dblp_xml.read_streams`, or re-exports `read_streams`. Pick one and keep the test consistent with it. Import `CrawlError` in the test from `sources.common` if `dblp.CrawlError` is not re-exported.)

```python
# backend/tests/unit/ingest/test_dblp_aaai_table.py
from datetime import date

import pytest
from openproceedings.ingest import dblp_aaai_table, dblp_table

GOOD = """
not_held = [1981, 1985, 1989, 2001, 2003, 2009]

[[year]]
year = 1986
proceedings = ["conf/aaai/1986-1", "conf/aaai/1986-2"]
papers = 4
title = "Synthetic AAAI 1986"
verified = 2026-10-10
source = "test"

[[year]]
year = 2006
proceedings = ["conf/aaai/2006"]
papers = 1
title = "Synthetic AAAI 2006"
verified = 2026-10-10
source = "test"

[[workshop]]
key = "conf/aaai/2006w"
year = 2006
papers = 1
title = "Synthetic AAAI 2006 workshop"
verified = 2026-10-10
source = "test"

[[not_paper]]
key = "conf/aaai/Invited86"
year = 1986
kind = "invited talk"
reason = "an invited talk's abstract in the proceedings"
"""


def test_loads_with_the_icml_tables_pin() -> None:
    t = dblp_aaai_table.load(GOOD)
    assert t.release == dblp_table.TABLE.release and t.dtd == dblp_table.TABLE.dtd  # one pin, never a second
    assert t.main_key("conf/aaai/1986-2").year == 1986 and t.main_key("conf/aaai/2006w") is None
    assert t.workshop("conf/aaai/2006w").papers == 1
    assert t.stated(2006) == 2 and t.stated(1986) == 4
    assert t.not_held == frozenset({1981, 1985, 1989, 2001, 2003, 2009})
    assert t.years[1986].verified == date(2026, 10, 10)
    assert (dblp_aaai_table.FIRST_YEAR, dblp_aaai_table.LAST_YEAR) == (1980, 2008)
    assert dblp_aaai_table.CHECKED == range(1980, 2010)


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        (lambda s: s.replace("year = 2006\nproceedings", "year = 2010\nproceedings"), "1980 to 2008"),
        (lambda s: s.replace("year = 1986\nproceedings", "year = 1985\nproceedings"), "both held and not held"),
        (lambda s: s.replace('"conf/aaai/2006"]', '"conf/icml/2006"]'), "conf/aaai/"),
        (lambda s: s.replace("papers = 4", "papers = 0"), "positive"),
        (lambda s: s.replace('key = "conf/aaai/2006w"\nyear = 2006', 'key = "conf/aaai/2006w"\nyear = 2005'),
         "a year the table holds"),
        (lambda s: s.replace('kind = "invited talk"', 'kind = "keynote speech"'), "kind"),
        (lambda s: s.replace("not_held = [1981,", "not_held = [1979,"), "1980 to 2009"),
        (lambda s: s.replace('key = "conf/aaai/2006w"', 'key = "conf/aaai/2006"'), "listed twice"),
        (lambda s: s + "\n[release]\ndoi = \"x\"\n", "unknown tables"),
    ],
)  # fmt: skip
def test_bad_rows_are_refused(edit, message) -> None:
    with pytest.raises(ValueError, match=message):
        dblp_aaai_table.load(edit(GOOD))


def test_the_shipped_table_loads_and_records_the_years_aaai_was_not_held() -> None:
    assert dblp_aaai_table.TABLE.not_held == frozenset({1981, 1985, 1989, 2001, 2003, 2009})
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest backend/tests/unit/ingest/test_dblp_slices.py backend/tests/unit/ingest/test_dblp_aaai_table.py -q`

Expected: FAIL (`ImportError: cannot import name 'read_streams'`; `ModuleNotFoundError: dblp_aaai_table`).

- [ ] **Step 3: Implement `read_streams`** (`dblp_xml.py`)

```python
def _start_tag(prefixes: tuple[str, ...]) -> re.Pattern[bytes]:
    types = "|".join(sorted(RECORD_TYPES)).encode()
    keys = b"|".join(re.escape(p.encode()) for p in prefixes)
    return re.compile(rb"<(" + types + rb')\s[^<>]*?\bkey="(?:' + keys + rb')[^"]*"[^<>]*>')
```

`_records(path, prefixes: tuple[str, ...], progress)` keeps today's logic with three changes:
- `markers = tuple(p.encode() for p in prefixes)`;
- the prefilter is `if end is None and not any(m in line for m in markers): continue`;
- `wanted = re.compile(rb"\bkey\s*=\s*[\"'](?:" + b"|".join(re.escape(m) for m in markers) + b")")`.

Error messages name `", ".join(prefixes)`, which reads exactly as before for one prefix.

```python
def read_streams(
    path: Path, dtd: bytes, dtd_name: str, prefixes: tuple[str, ...],
    progress: Callable[[int, int], None] | None = None,
) -> dict[str, list[DblpEntry]]:  # fmt: skip
    """Every record of the release at `path` whose key starts with one of `prefixes`, per prefix, in file order:
    one streaming read for all of them (decision-049: ICML and AAAI from one pass). No prefix may start another."""
    if len(set(prefixes)) != len(prefixes) or any(a != b and a.startswith(b) for a in prefixes for b in prefixes):
        raise ValueError(f"prefixes must be distinct and none may start another: {prefixes}")
    if (named := doctype_system_id(path)) != dtd_name:
        raise DblpFormatError(f"the release names DTD {named!r}, not the pinned {dtd_name!r}")
    out: dict[str, list[DblpEntry]] = {p: [] for p in prefixes}
    for block in _records(path, prefixes, progress):
        e = _parse(block, dtd, dtd_name)
        owner = next((p for p in prefixes if e.key.startswith(p)), None)
        if owner is None:
            raise DblpFormatError(f"record {e.key!r} isn't in {', '.join(prefixes)}")
        out[owner].append(e)
    return out


def read_stream(path: Path, dtd: bytes, dtd_name: str, prefix: str,
                progress: Callable[[int, int], None] | None = None) -> list[DblpEntry]:  # fmt: skip
    """One prefix's records (`read_streams` with one prefix)."""
    return read_streams(path, dtd, dtd_name, (prefix,), progress)[prefix]
```

- [ ] **Step 4: Implement the slices** (`dblp.py`)

```python
@dataclass(frozen=True, slots=True)
class Slice:
    """One venue's records in the release: its key prefix and where its extract lives. ICML's file predates the
    slices and keeps its path (`subdir` ""), so its markers replay the same bytes (guarantee 4)."""

    venue: str
    prefix: str
    subdir: str

    def path(self, cache: Path, table: Table = TABLE) -> Path:
        return cache / CACHE_DIR / "extract" / self.subdir / f"{table.release.file.sha256}.json"


ICML_SLICE = Slice("ICML", PREFIX, "")
AAAI_SLICE = Slice("AAAI", "conf/aaai/", "aaai")
SLICES = (ICML_SLICE, AAAI_SLICE)


def extract_path(cache: Path, table: Table = TABLE) -> Path:
    return ICML_SLICE.path(cache, table)
```

`write_extracts(cache, release, dtd, table=TABLE, slices=(ICML_SLICE,), monotonic=time.monotonic)` works like this:
- It does today's `write_extract` body once, with `read_streams(..., tuple(s.prefix for s in slices), progress)`.
- Per slice, it writes the same JSON body as today (same keys, `EXTRACT_FORMAT`, `fetched_at = release.fetched_at`) to `s.path(cache, table)`.
- It logs one `dblp_extract_written` line per slice, with `venue`.
- It returns `{s.venue: Extract(...)}`.

`write_extract(...)` becomes `return write_extracts(cache, release, dtd, table, (ICML_SLICE,), monotonic)["ICML"]`.

`load_extract(cache, table=TABLE, slice_=ICML_SLICE)` reads `slice_.path(...)`. It adds, inside the `try`:

```python
        if any(not e.key.startswith(slice_.prefix) for e in entries):
            raise ValueError(f"holds a record outside {slice_.prefix}")
```

The `not_cached` message says `run op ingest dblp --venue {slice_.venue}`.

```python
def prepare_slices(cache: Path, stream: StreamTransport | None, table: Table = TABLE,
                   slices: tuple[Slice, ...] = SLICES) -> dict[str, Extract]:  # fmt: skip
    """The pinned release on disk and each wanted slice's extract: read back when the release was already verified on
    disk and its file is current, else written. Whenever the release must be read, one pass writes every slice whose
    extract is missing, wanted or not. One run at a time (`<cache>/dblp/.lock`). No table check here: each venue's
    own `check_extract` runs on its slice."""
    with storage.exclusive(cache / CACHE_DIR):
        release, dtd = fetch_release(cache, stream, table)
        out: dict[str, Extract] = {}
        missing: list[Slice] = []
        for s in slices:
            if release.cached and s.path(cache, table).exists():
                try:
                    out[s.venue] = load_extract(cache, table, s)
                    continue
                except CrawlError as e:
                    log.info("dblp_extract_stale", extra={"doi": table.release.doi, "venue": s.venue, "reason": e.reason})
            missing.append(s)
        if missing:
            extra = [s for s in SLICES if s not in missing and not s.path(cache, table).exists()]
            written = write_extracts(cache, release, dtd, table, (*missing, *extra))
            out |= {s.venue: written[s.venue] for s in missing}
    return out


def prepare(cache: Path, stream: StreamTransport | None, table: Table = TABLE) -> Extract:
    """ICML's extract, checked against its table (unchanged behaviour)."""
    extract = prepare_slices(cache, stream, table, (ICML_SLICE,))["ICML"]
    check_extract(extract, table)
    return extract
```

Update the module docstring's step 2: "reads its `conf/icml/` and `conf/aaai/` records once, streaming, into one extract per venue (`<cache>/dblp/extract/<sha256>.json` for ICML, `…/extract/aaai/<sha256>.json` for AAAI)".

- [ ] **Step 5: Implement `dblp_aaai_table.py`**

Follow `dblp_table.py`'s style: frozen slotted dataclasses, `MappingProxyType`, `_check` for columns. Module docstring: the table's purpose, that the pin is `dblp_icml.toml`'s, and what each table means (copy the TOML header below).

```python
FIRST_YEAR, LAST_YEAR = DBLP_YEARS["AAAI"][0], DBLP_YEARS["AAAI"][-1]  # 1980, 2008: OJS from 2010
CHECKED = range(FIRST_YEAR, LAST_YEAR + 2)  # 1980-2009: every conf/aaai/ proceedings key dated in it is classified
_KEY = re.compile(r"conf/aaai/[A-Za-z0-9_-]+")
NOT_PAPER_KINDS = frozenset({"invited talk", "panel", "front matter", "tutorial summary", "workshop summary"})
_TABLES = {"not_held", "year", "workshop", "excluded", "not_paper"}
```

Dataclasses:
- `AaaiYear(year, proceedings: tuple[str, ...], papers, title, verified, source)`;
- `Workshop(key, year, papers, title, verified, source)`;
- `Excluded(key, year, reason)`;
- `NotPaper(key, year, kind, reason)`;
- `Table(release, dtd, years, workshops, excluded, not_papers, not_held: frozenset[int])`, with:

```python
    def main_key(self, crossref: str | None) -> AaaiYear | None:
        return next((y for y in self.years.values() if crossref in y.proceedings), None)

    def workshop(self, crossref: str | None) -> Workshop | None:
        return self.workshops.get(crossref or "")

    def stated(self, year: int) -> int:
        return self.years[year].papers + sum(w.papers for w in self.workshops.values() if w.year == year)
```

`load(text: str, pins: dblp_table.Table | None = None) -> Table` validates the following, each as a `ValueError` whose message contains the phrase the tests match:
- **Tables:** only the `_TABLES` keys ("unknown tables").
- **`not_held`:** a list of distinct ints in `CHECKED` ("1980 to 2009").
- **`[[year]]`:** columns `year, proceedings, papers, title, verified, source`; year in `FIRST_YEAR..LAST_YEAR` ("1980 to 2008") and not in `not_held` ("both held and not held"); `venue_name("AAAI", year)`; proceedings a non-empty list of `_KEY` strings ("conf/aaai/"); papers a positive int ("positive"); a non-empty title, a date and a source.
- **`[[workshop]]`:** same scalar columns; key `_KEY`; year in the table's years ("a year the table holds").
- **`[[excluded]]`:** key `_KEY`; year in `CHECKED`; a non-empty reason.
- **`[[not_paper]]`:** key `_KEY`; year in the table's years; kind in `NOT_PAPER_KINDS` ("kind"); a non-empty reason.
- **Keys:** no key appears twice across main, workshop and excluded, and no `not_paper` key is a proceedings key ("listed twice").

It returns `Table(pins.release, pins.dtd, …)` with `pins = pins or dblp_table.TABLE`.

```python
TABLE: Table = load(files("openproceedings.ingest").joinpath("dblp_aaai.toml").read_text(encoding="utf-8"))
```

`dblp_aaai.toml` (shipped now with no year rows; Task 8 adds them):

```toml
# The dblp AAAI table (spec 01 §Sources, dblp row; decision-049, milestone B). Data, not code:
# `ingest/dblp_aaai_table.py` loads and checks it, and `ingest/sources/dblp_aaai.py` reads AAAI 1980-2008 through
# it. The release is the one `dblp_icml.toml` pins (one file, read once for both venues): this table names no pin.
#
# not_held      the years 1980-2009 with no AAAI conference; a conf/aaai/ proceedings key dblp dates to one stops
#               the ingest
# [[year]]      one AAAI year: its main conference's proceedings key(s) (1986, 1991, 1994 and 1996 have two), the
#               inproceedings the pinned release lists under them when verified, dblp's proceedings title
# [[workshop]]  a conf/aaai/ workshop proceedings key of 1980-2008: its papers are track `workshop`
# [[excluded]]  any other conf/aaai/ proceedings key dated 1980-2009, with why it is not read
# [[not_paper]] an entry under a main or workshop key that is no paper (an invited talk, a panel): counted in its
#               year's listing, never a record
# dblp's conf/aaai/ keys dated 2010 or later are never read: ojs.aaai.org holds those years (ojs_sections.toml).
not_held = [1981, 1985, 1989, 2001, 2003, 2009]
```

- [ ] **Step 6: Run and commit**

Run: `uv run pytest backend/tests/unit/ingest -q -n auto`. Expected: PASS. Every `test_dblp.py` and `test_dblp_xml.py` test passes unchanged.

```bash
git add -A backend
git commit -m "feat: one dblp release pass writes each venue's extract (ICML's path and bytes kept); the dblp AAAI table loader"
```

---

### Task 4: AAAI 1980–2008 records, `op ingest dblp --venue AAAI`, replay, coverage scope

**Files:**
- Create: `backend/src/openproceedings/ingest/sources/dblp_aaai.py`
- Modify: `backend/src/openproceedings/ingest/sources/dblp.py:422-443` (`links(..., pdf_hosts=PDF_HOSTS)`)
- Modify: `backend/src/openproceedings/ingest/urls.py:106-148` (`dblp_aaai`, `native`)
- Modify: `backend/src/openproceedings/eval/scholar_compare.py` (`proceedings_key`: a dblp AAAI page names no key)
- Modify: `backend/src/openproceedings/ingest/sources/crawl.py` (`ingest_dblp_aaai`, `_replay_dblp_aaai`, `DBLP_AAAI`, `SOURCES`, docstring)
- Modify: `backend/src/openproceedings/cli.py:140-187, 581-597` (`--venue` on `dblp`; dispatch)
- Modify: `backend/src/openproceedings/eval/coverage_report.py:443-468` (`_scope`)
- Create: `backend/tests/unit/ingest/test_dblp_aaai.py`; Modify: `backend/tests/unit/ingest/test_urls.py`, `backend/tests/unit/test_cli.py`, `backend/tests/unit/test_coverage_report.py`, `backend/tests/unit/ingest/ojs/test_ojs_crawl.py:44` (the SOURCES order test moves to Task 7's final order; here assert `crawl.SOURCES[-1] is crawl.DBLP_AAAI`)

**Interfaces:**
- Consumes: Task 3 (`AAAI_SLICE`, `prepare_slices`, `load_extract`, `dblp_aaai_table`); Task 1 (AAAI `dblp-` ids).
- Produces:
  - `dblp_aaai.SOURCE = "dblp"`, `dblp_aaai.PREFIX = "conf/aaai/"`;
  - `dblp_aaai.check_extract(extract, table=None)`;
  - `dblp_aaai.mine_year(year, extract, *, table=None) -> dblp.YearResult` (it raises `count_mismatch`, so a replay stops too);
  - `urls.dblp_aaai(url) -> str | None`;
  - `crawl.ingest_dblp_aaai(years, cache, *, offline=False, dry_run=False, stream=None, table=DBLP_TABLE, aaai=None) -> dict`;
  - `crawl.DBLP_AAAI: Crawls[dblp.YearResult]`, keyed `(year, release)`, with markers `<cache>/dblp/aaai-crawls/<year>.json` = `{"source": "dblp", "venue": "AAAI", "year": Y, "release": "<doi>"}`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/unit/ingest/test_dblp_aaai.py
"""AAAI 1980-2008 from the pinned dblp release (decision-049, milestone B): the check, the records, the counts, the
replay. Synthetic release (test_dblp_slices.AAAI_BODY). No network."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from openproceedings.ingest import dblp_aaai_table, urls
from openproceedings.ingest.dedup import dedup
from openproceedings.ingest.sources import crawl, dblp, dblp_aaai
from openproceedings.ingest.sources.common import CrawlError
from openproceedings.ingest.statuses import statuses_indexed

from tests.unit.ingest.test_dblp_aaai_table import GOOD
from tests.unit.ingest.test_dblp_slices import GZ_FULL, on_disk
from tests.unit.ingest.test_dblp_xml import DTD, Stream


def setup(tmp_path: Path, text: str = GOOD):
    table, rel, dtd = on_disk(tmp_path)
    aaai = dblp_aaai_table.load(text, pins=table)
    extract = dblp.write_extracts(tmp_path, rel, dtd, table, dblp.SLICES)["AAAI"]
    return table, aaai, extract


def test_aaai_records_from_the_release(tmp_path: Path) -> None:
    _table, aaai, extract = setup(tmp_path)
    dblp_aaai.check_extract(extract, aaai)
    (report,), records = (r := dblp_aaai.mine_year(1986, extract, table=aaai)).reports, {x.id: x for x in r.records}
    assert set(records) == {"op:aaai:1986:dblp-Synthetic86a", "op:aaai:1986:dblp-Synthetic86b"}
    a = records["op:aaai:1986:dblp-Synthetic86a"]
    assert (a.venue, a.year, a.track, a.status, a.title, a.abstract) == (
        "AAAI", 1986, "main", "accepted", "Synthetic AAAI title 1", None)
    assert a.authors == ("Synthetic Author 1", "Synthütic Author 2")  # the homonym number dropped, the entity read
    assert a.urls.proceedings == "https://dblp.org/rec/conf/aaai/Synthetic86a" and a.urls.doi == "10.5555/synthetic.1"
    assert a.urls.pdf is None and {c.source for c in a.provenance} == {"dblp"}
    assert records["op:aaai:1986:dblp-Synthetic86b"].title == "Synthetic AAAI title 2?"
    assert (report.venue, report.stated, report.listed, report.records, report.count_ok) == ("AAAI", 4, 4, 2, True)
    assert report.skipped == {"not_paper": 1, "publtype_withdrawn": 1}


def test_a_workshop_key_gives_track_workshop(tmp_path: Path) -> None:
    _t, aaai, extract = setup(tmp_path)
    tracks = {r.native: r.track for r in dblp_aaai.mine_year(2006, extract, table=aaai).records}
    assert tracks == {"dblp-Main06": "main", "dblp-Workshop06": "workshop"}


@pytest.mark.parametrize(("raw", "kept"), [("Wei Wang 0001", "Wei Wang"), ("Wei Wang 0042", "Wei Wang"),
                                           ("A. B. 12", "A. B. 12"), ("Ada 0001x", "Ada 0001x")])  # fmt: skip
def test_clean_author_drops_only_a_four_digit_homonym(raw: str, kept: str) -> None:
    assert dblp.clean_author(raw) == kept


def test_a_count_that_differs_from_the_table_stops_the_year_and_its_replay(tmp_path: Path) -> None:
    _t, aaai, extract = setup(tmp_path, GOOD.replace("papers = 4", "papers = 5"))
    with pytest.raises(CrawlError, match="1986") as e:
        dblp_aaai.mine_year(1986, extract, table=aaai)
    assert e.value.reason == "count_mismatch"


@pytest.mark.parametrize(
    ("edit", "reason"),
    [(lambda s: s.replace('"conf/aaai/2006"]', '"conf/aaai/2007"]').replace("year = 2006\nproceedings", "year = 2007\nproceedings"), "unlisted_proceedings"),
     (lambda s: s.replace("not_held = [1981, 1985, 1989, 2001, 2003, 2009]", "not_held = [1981, 1985, 1989, 2001, 2003, 2006, 2009]")
      .split("[[year]]\nyear = 2006")[0], "table_mismatch"),
     (lambda s: s.replace('key = "conf/aaai/Invited86"', 'key = "conf/aaai/Nowhere86"'), "table_mismatch")],
)  # fmt: skip
def test_the_check_stops_on_an_unlisted_key_a_not_held_year_or_an_absent_row(tmp_path: Path, edit, reason) -> None:
    _t, aaai, extract = setup(tmp_path, edit(GOOD))
    with pytest.raises(CrawlError) as e:
        dblp_aaai.check_extract(extract, aaai)
    assert e.value.reason == reason


def test_2010_on_is_never_read(tmp_path: Path) -> None:
    _t, aaai, extract = setup(tmp_path)
    dblp_aaai.check_extract(extract, aaai)  # conf/aaai/2024 is in the extract and unlisted: ignored
    with pytest.raises(CrawlError):
        dblp_aaai.mine_year(2024, extract, table=aaai)


def test_an_aaai_dblp_record_names_itself_and_passes_dedup(tmp_path: Path) -> None:
    _t, aaai, extract = setup(tmp_path)
    records = dblp_aaai.mine_year(1986, extract, table=aaai).records
    assert len(dedup(records).records) == 2  # dedup's self-naming check: urls.native reads /rec/conf/aaai/
    assert urls.native("https://dblp.org/rec/conf/aaai/Synthetic86a") == "dblp-Synthetic86a"
    assert statuses_indexed(["dblp"], "AAAI", 1986) == ["accepted"]


def test_ingest_marks_each_year_and_the_replay_rebuilds_it(tmp_path: Path, monkeypatch) -> None:
    table, aaai, _ = setup(tmp_path)
    monkeypatch.setattr(dblp_aaai, "TABLE", aaai)
    out = crawl.ingest_dblp_aaai(range(1985, 1987), tmp_path, offline=True, table=table, aaai=aaai)
    assert out["not_held"] == [1985] and [x["year"] for x in out["listings"]] == [1986]
    marker = json.loads((tmp_path / "dblp" / "aaai-crawls" / "1986.json").read_text())
    assert marker == {"source": "dblp", "venue": "AAAI", "year": 1986, "release": table.release.doi}
    assert not (tmp_path / "dblp" / "crawls").exists()  # ICML's replay never sees an AAAI marker
    monkeypatch.setattr(crawl, "DBLP_TABLE", table)
    (replayed,) = crawl.DBLP_AAAI.replay(tmp_path)
    assert sorted(r.id for r in replayed.records) == ["op:aaai:1986:dblp-Synthetic86a", "op:aaai:1986:dblp-Synthetic86b"]


def test_a_year_outside_the_table_is_refused(tmp_path: Path) -> None:
    table, aaai, _ = setup(tmp_path)
    with pytest.raises(CrawlError, match="AAAI 1990"):
        crawl.ingest_dblp_aaai([1990], tmp_path, offline=True, table=table, aaai=aaai)
```

Notes for the implementer:
- `_replay_dblp_aaai` takes `table=DBLP_TABLE` as a default argument, captured when the function is defined. Either read `crawl.DBLP_TABLE` at call time, or pass the test table through, so the monkeypatch above works. Pick one and adjust the test.
- `test_urls.py`:

```python
@pytest.mark.parametrize(("url", "key"), [("https://dblp.org/rec/conf/aaai/Smith90", "Smith90"),
    ("http://DBLP.org/rec/conf/aaai/Smith90.html", "Smith90"), ("https://dblp.org/rec/conf/icml/Smith90", None),
    ("https://dblp.org/rec/conf/aaai/2006w", "2006w"), ("https://example.org/rec/conf/aaai/Smith90", None)])  # fmt: skip
def test_dblp_aaai(url: str, key: str | None) -> None:
    assert urls.dblp_aaai(url) == key
```

- `test_scholar_compare.py`: `assert proceedings_key("https://dblp.org/rec/conf/aaai/Smith90") is None`.
- `test_cli.py`: `op ingest dblp --venue AAAI --year 1980-2008 --offline` dispatches to `ingest_dblp_aaai(range 1980..2008, …, offline=True)` (monkeypatch `crawl.ingest_dblp_aaai` to record its arguments). `op ingest dblp --year 1990` still dispatches to `ingest_dblp`. `op ingest dblp --venue AAAI --year 1990 --refresh` exits 2 with `nothing to refresh`.
- `test_coverage_report.py`: a manifest with one ICML and one AAAI dblp listing renders `- ICML 1990–1990: …` and `- AAAI 1986–1986: …`, never `ICML 1986`.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest backend/tests/unit/ingest/test_dblp_aaai.py -q`. Expected: FAIL (`ImportError: dblp_aaai`).

- [ ] **Step 3: Implement `sources/dblp_aaai.py`**

```python
"""AAAI 1980-2008 from the pinned dblp release (spec 01 §Sources, dblp row; decision-049, milestone B).

ojs.aaai.org starts at AAAI 2010 (Vol. 24); the earlier proceedings are on aaai.org, whose robots.txt asks for 12 h
between requests and whose pages give no abstracts. dblp lists them under `conf/aaai/<year>` (1986, 1991, 1994 and
1996 in two volumes). The release is the one ICML reads (`dblp_table.TABLE`'s pin), read in the same streaming pass
into AAAI's own extract (`dblp.AAAI_SLICE`). `dblp_aaai_table.TABLE` names each year's main-conference keys, the
workshop keys (track `workshop`), the `[[not_paper]]` entries (counted, never records) and the years AAAI was not
held. A `conf/aaai/` proceedings key dated 1980-2009 the table doesn't classify, a not-held year dblp holds a key
for, a row whose key the release lacks, or a count that differs from the table's stops the ingest, and the count
check runs again in every replay. dblp's AAAI keys of 2010 on are never read. Fields as for ICML (`dblp.py`):
title without dblp's closing period, authors without homonym numbers, `urls.doi` from a DOI `ee`, `urls.proceedings`
the dblp record page (linked, never fetched). No abstracts. Every record is `accepted`.
"""
```

Constants: `SOURCE: Source = "dblp"`, `PREFIX = "conf/aaai/"`, `NATIVE = dblp.NATIVE`.

`check_extract(extract, table=None)`, with `table = table or TABLE`:
1. For each `proceedings` entry, read its `year` (None if not digits) and skip it if `year is not None and year not in CHECKED`.
   - A year in `table.not_held` raises `table_mismatch`: `"dblp dates {key} to {year}, a year dblp_aaai.toml records AAAI as not held"`.
   - An entry that is neither `table.main_key` nor `table.workshop` nor excluded raises `unlisted_proceedings`, with ICML's wording and `dblp_aaai.toml`.
2. Every main and workshop key the table names must be in the release under its year, else `table_mismatch` (an absent table unit).
3. Every `not_paper` key must be an inproceedings whose crossref is one of its year's main or workshop keys, else `table_mismatch`.

`mine_year(year, extract, *, table=None)`:
- Raise `not_held` for a not-held year, and `no_year` for a year the table lacks.
- Build `by_key = {k: ("main", "main") for k in row.proceedings} | {w.key: ("workshop", w.key) for w in workshops of year}`. The second element names the count group.
- Walk the inproceedings:
  - one whose crossref is not in `by_key` but whose year matches is counted `excluded_proceedings` or `no_main_crossref` (as ICML does);
  - any other counts in `report.listed` and in its group.
- For each listed entry, in order:
  - a tail failing `NATIVE` raises `unparsed_key`;
  - a not-paper key is counted `not_paper`;
  - a `publtype` is counted `publtype_<it>`;
  - a key already seen is counted `duplicate`;
  - anything else is kept with its track.
- Compare each group's listed count with its verified count (`row.papers` for main, `w.papers` per workshop). Any difference raises `count_mismatch`: `"AAAI {year}: release {doi} lists {n} under {keys}, the table verified {m}"`.
- Build each record with `_record`. An invalid record is counted `invalid`, with the `listing_attention` warning, as ICML does.
- Use `report = dblp.DblpReport(SOURCE, "AAAI", year, table.release.doi_url, "primary", table.stated(year))` with `report.fetched.append(extract.fetched_at)`.
- Log `dblp_aaai_year_mined` (year, listed, stated, records, ms).
- Return `dblp.YearResult(records, [report])`.

`_record(year, tail, e, track, extract, table)` mirrors `dblp._record`:
- `where = f"dblp record {e.key} in release {doi} (sha256 {sha[:16]})"`;
- claims for venue `AAAI`, year (`"; AAAI {year} by dblp_aaai.toml"`), title, authors (homonyms dropped), track (`f"crossref {e.fields['crossref']}: AAAI {year} {'main conference' if track == 'main' else 'workshop'} (dblp_aaai.toml)"`) and status;
- links from `dblp.links(e.key, e.lists.get("ee", []), pdf_hosts=frozenset())`;
- returns `record_from_claims(f"op:aaai:{year}:dblp-{tail}", claims)`.

In `dblp.links`, add the `pdf_hosts: frozenset[str] = PDF_HOSTS` parameter, used where `PDF_HOSTS` is today.

- [ ] **Step 4: Implement urls, scholar_compare, crawl, CLI, coverage**

`urls.py`:

```python
_DBLP_REC_AAAI = re.compile(r"/rec/conf/aaai/([A-Za-z0-9_-]+)(?:\.html)?")


def dblp_aaai(url: str) -> str | None:
    """The key after `conf/aaai/` of a dblp record page URL (AAAI 1980-2008; decision-049), or None."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or parsed.netloc.lower() != "dblp.org":
        return None
    m = _DBLP_REC_AAAI.fullmatch(parsed.path)
    return m.group(1) if m else None
```

In `native()`, after the ICML dblp branch: `if (key := dblp_aaai(url)) is not None: return f"dblp-{key}"`. Update the docstring.

`crawl.py`:

```python
from openproceedings.ingest import dblp_aaai_table
from openproceedings.ingest.sources import dblp_aaai


def ingest_dblp_aaai(
    years: Iterable[int], cache: Path, *, offline: bool = False, dry_run: bool = False,
    stream: StreamTransport | None = None, table: DblpTable = DBLP_TABLE, aaai: dblp_aaai_table.Table | None = None,
) -> dict[str, Any]:  # fmt: skip
    """AAAI years from the pinned dblp release (decision-049, milestone B): not-held years are skipped and named; a
    dry run fetches nothing and says whether the release and AAAI's extract are on disk."""
    aaai = aaai or dblp_aaai_table.TABLE
    asked = sorted(set(years))
    not_held = [y for y in asked if y in aaai.not_held]
    wanted = [y for y in asked if y not in aaai.not_held]
    if missing := [y for y in wanted if y not in aaai.years]:
        span = f"{min(aaai.years)}-{max(aaai.years)}" if aaai.years else "no years yet"
        raise MinerError(f"AAAI {missing[0]}: dblp_aaai.toml covers AAAI {span} (OJS from 2010)", reason="no_year")
    if dry_run:
        return {"dry_run": True, "release_on_disk": dblp.release_on_disk(cache, table),
                "extract_on_disk": dblp.AAAI_SLICE.path(cache, table).exists(), "years": wanted, "not_held": not_held}  # fmt: skip
    extract = dblp.prepare_slices(cache, None if offline else (stream or urllib_stream), table, (dblp.AAAI_SLICE,))["AAAI"]
    dblp_aaai.check_extract(extract, aaai)
    mined = DBLP_AAAI.ingest(
        cache, wanted, lambda year: dblp_aaai.mine_year(year, extract, table=aaai),
        lambda year, _: (str(year), {"source": dblp.SOURCE, "venue": "AAAI", "year": year, "release": table.release.doi}),
    )  # fmt: skip
    reports = [r for m in mined for r in m.reports]
    log.info("dblp_aaai_ingested", extra={"years": len(reports), "not_held": len(not_held)})
    return {"dry_run": False, "listings": [r.to_manifest() for r in reports], "not_held": not_held}


def _aaai_key(m: Mapping[str, Any]) -> tuple[Any, ...]:
    if m["venue"] != "AAAI":
        raise ValueError("not an AAAI marker")
    return (int(m["year"]), str(m["release"]))


def _replay_dblp_aaai(cache: Path, key: tuple[Any, ...]) -> dblp.YearResult:
    year, release = key
    if release != DBLP_TABLE.release.doi:
        raise MinerError(f"AAAI {year} was ingested from dblp release {release}, not the pinned "
                         f"{DBLP_TABLE.release.doi}; re-run op ingest dblp --venue AAAI", reason="release_changed")  # fmt: skip
    return dblp_aaai.mine_year(year, dblp.load_extract(cache, DBLP_TABLE, dblp.AAAI_SLICE))


DBLP_AAAI: Crawls[dblp.YearResult] = Crawls(
    lambda cache: cache / dblp.CACHE_DIR / "aaai-crawls", _aaai_key,
    lambda k: f"AAAI {k[0]} (dblp)", "op ingest dblp --venue AAAI", _replay_dblp_aaai,
)  # fmt: skip
SOURCES = (openreview_v2.CRAWLS, openreview_v1.CRAWLS, ICLR, NEURIPS, PMLR, DBLP, OJS, DBLP_AAAI)
```

`DBLP_TABLE` is read at call time inside `_replay_dblp_aaai`, so a test can monkeypatch it. Update the module docstring's replay order.

`cli.py`:
- In the crawl-parser loop, for `name in ("dblp", "pmlr")`: `crawl.add_argument("--venue", default="ICML", choices=("ICML", "AAAI") if name == "dblp" else ("ICML", "FAccT"), help="…")`. The pmlr choices are wired in Task 5. Until then `FAccT` is refused in `_ingest_crawl` with `_usage("…arrives with the v81 row")`, or add the choice only in Task 5.
- The dblp help names AAAI 1980–2008 and `ingest/dblp_aaai.toml`.
- In `_ingest_crawl`, for `ns.source == "dblp" and ns.venue == "AAAI"`: refuse `--refresh` (`_usage("--refresh: nothing to refresh for AAAI (the release is pinned; no pages are fetched)")`), then `_print(ingest_dblp_aaai(years, ns.data_dir / "cache", offline=ns.offline, dry_run=ns.dry_run))`.

`coverage_report._scope`:
- `dblp = [x for x in listings if x.get("venue", "ICML") == "ICML"]` keeps today's ICML sentence byte for byte.
- Add, when AAAI dblp listings exist: `f"- AAAI {held[0]}–{held[-1]}: from the pinned dblp snapshot release {', '.join(releases)} (a bibliography read from one pinned file; decision-049). Its {records:,} records have no abstract (dblp holds none)."`

- [ ] **Step 5: Run the full backend suite and commit**

Run: `uv run pytest backend/tests -q -n auto` and `make lint`. Expected: PASS.

```bash
git add -A backend
git commit -m "feat: AAAI 1980-2008 from the pinned dblp release (op ingest dblp --venue AAAI; its own markers and replay; counts stop)"
```

---

### Task 5: PMLR v81: FAccT 2018 without loosening ICML

**Files:**
- Modify: `backend/src/openproceedings/ingest/volumes.py` (docstring, `PMLR_VENUES`, `not_papers` column, `Volume.not_papers`, `PMLR_NATIVE_VOLUMES`, `ingested_volume`; `ICML_PMLR_VOLUMES` and `icml_volume` unchanged in result)
- Modify: `backend/src/openproceedings/ingest/pmlr_volumes.toml` (header: the `venue` line names FAccT, the `not_papers` column documented; the v81 row arrives in Task 9)
- Modify: `backend/src/openproceedings/ingest/sources/pmlr.py:1-14, 65-76, 158-243, 291`
- Modify: `backend/src/openproceedings/ingest/record.py` (`PROCEEDINGS_NATIVE["pmlr"]` venues; the non-ICML `pmlr-` check)
- Modify: `backend/src/openproceedings/ingest/urls.py:111` (`native()` reads `volumes.PMLR_NATIVE_VOLUMES`)
- Modify: `backend/src/openproceedings/eval/scholar_compare.py` (`proceedings_key` from `PMLR_NATIVE_VOLUMES`)
- Modify: `backend/src/openproceedings/ingest/sources/crawl.py:114-139` (`ingest_pmlr(..., venue="ICML")`), `cli.py` (`--venue` for pmlr)
- Test: `backend/tests/unit/ingest/test_pmlr.py`, `test_record.py`, `test_urls.py`, `test_ris.py`, `backend/tests/unit/test_scholar_compare.py`

**Interfaces:**
- Produces:
  - `volumes.PMLR_VENUES = frozenset({"ICML", "FAccT"})`;
  - `volumes.Volume.not_papers: tuple[str, ...] = ()`;
  - `volumes.PMLR_NATIVE_VOLUMES: Mapping[int, tuple[str, int, str]]` ((venue, year, track) of every ingested volume);
  - `volumes.ingested_volume(venue, year) -> Volume | None`;
  - `crawl.ingest_pmlr(years, cache, *, venue="ICML", …)`.
- `record.py` and `urls.py` read `volumes.PMLR_NATIVE_VOLUMES` **through the module at call time** (`from openproceedings.ingest import volumes as _volumes`), so tests monkeypatch it.

- [ ] **Step 1: Write the failing tests** (append to `test_pmlr.py`)

```python
from openproceedings.ingest import volumes
from openproceedings.ingest.dedup import dedup

FACCT = """
[[volume]]
number = 81
venue = "FAccT"
year = 2018
track = "main"
role = "primary"
papers = 3
not_papers = ["preface18a"]
heading = "Conference on Fairness, Accountability and Transparency"
verified = 2026-10-10
source = "test"
"""
V81_INDEX = """<html><body><h1>Volume 81: Conference on Fairness, Accountability and Transparency, 23-24 February 2018,
New York, NY, USA</h1>
<div class="paper"><p class="title">Synthetic preface</p><span class="authors">Synthetic Editor</span>
<a href="https://proceedings.mlr.press/v81/preface18a.html">abs</a></div>
<div class="paper"><p class="title">Synthetic title 1</p><span class="authors">Synthetic Author 1, Synthetic Author 2</span>
<a href="https://proceedings.mlr.press/v81/one18a.html">abs</a>
<a href="https://proceedings.mlr.press/v81/one18a/one18a.pdf">pdf</a></div>
<div class="paper"><p class="title">Synthetic title 2</p><span class="authors">Synthetic Author 3</span>
<a href="https://proceedings.mlr.press/v81/two18a.html">abs</a></div>
</body></html>"""


@pytest.fixture
def facct_table(monkeypatch):
    table = {**volumes.VOLUMES, **load(FACCT)}
    native = {**volumes.PMLR_NATIVE_VOLUMES, 81: ("FAccT", 2018, "main")}
    monkeypatch.setattr(volumes, "VOLUMES", table)
    monkeypatch.setattr(pmlr, "VOLUMES", table)
    monkeypatch.setattr(volumes, "PMLR_NATIVE_VOLUMES", native)
    return table


def seed_v81(cache: Path, index: str = V81_INDEX) -> None:
    seed(cache, "pmlr", "https://proceedings.mlr.press/v81/", index)
    for key in ("one18a", "two18a"):
        seed(cache, "pmlr", f"https://proceedings.mlr.press/v81/{key}.html", "", status=404)


def test_v81_is_faccts_2018_and_the_preface_is_counted_never_a_record(tmp_path: Path, facct_table) -> None:
    seed_v81(tmp_path)
    result = mine(tmp_path, 81)
    assert sorted(r.id for r in result.records) == ["op:facct:2018:pmlr-v81-one18a", "op:facct:2018:pmlr-v81-two18a"]
    r = next(r for r in result.records if r.native == "pmlr-v81-one18a")
    assert (r.venue, r.year, r.track, r.status) == ("FAccT", 2018, "main", "accepted")
    assert r.urls.pdf == "https://proceedings.mlr.press/v81/one18a/one18a.pdf"
    report = result.report
    assert (report.venue, report.stated, report.listed, report.records, report.count_ok) == ("FAccT", 3, 3, 2, True)
    assert report.skipped == {"not_paper": 1}
    assert "https://proceedings.mlr.press/v81/preface18a.html" not in [p for p in (tmp_path / "pmlr").rglob("*.json")]
    assert len(dedup(result.records).records) == 2  # each names itself: urls.native knows v81


def test_a_non_icml_volume_whose_count_differs_stops(tmp_path: Path, facct_table) -> None:
    seed_v81(tmp_path, V81_INDEX.replace('<div class="paper"><p class="title">Synthetic title 2', '<div class="x"><p class="title">Synthetic title 2'))
    with pytest.raises(MinerError) as e:
        mine(tmp_path, 81)
    assert e.value.reason == "count_mismatch"


def test_a_not_paper_key_the_index_lacks_stops(tmp_path: Path, facct_table) -> None:
    seed_v81(tmp_path, V81_INDEX.replace("preface18a", "other18a"))
    with pytest.raises(MinerError) as e:
        mine(tmp_path, 81)
    assert e.value.reason in ("count_mismatch", "stale_not_paper")


def test_icml_is_untouched() -> None:
    assert set(volumes.ICML_PMLR_VOLUMES) == {28, 32, 37, 48, 70, 80, 97, 119, 139, 162, 202, 235, 267}
    assert volumes.icml_volume(2013).number == 28 and volumes.ingested_volume("ICML", 2013).number == 28


@pytest.mark.parametrize(
    ("row", "error"),
    [(FACCT.replace('venue = "FAccT"', 'venue = "AIES"'), "only ICML and FAccT"),
     (FACCT.replace('role = "primary"', 'role = "confirm"'), "primary"),
     (FACCT.replace('not_papers = ["preface18a"]', 'not_papers = ["a", "a"]'), "not_papers"),
     (FACCT.replace('not_papers = ["preface18a"]', 'not_papers = ["a b"]'), "not_papers"),
     (FACCT.replace("papers = 3", "papers = 1"), "fewer not_papers than papers")],
)  # fmt: skip
def test_a_malformed_non_icml_row_is_refused(row: str, error: str) -> None:
    with pytest.raises(ValueError, match=error):
        load(row)
```

`test_record.py`:

```python
def test_a_faccts_pmlr_id_must_name_its_own_volume_and_year(monkeypatch) -> None:
    monkeypatch.setattr(volumes, "PMLR_NATIVE_VOLUMES", {**volumes.PMLR_NATIVE_VOLUMES, 81: ("FAccT", 2018, "main")})
    assert _rec("op:facct:2018:pmlr-v81-one18a", "FAccT", 2018).native == "pmlr-v81-one18a"
    for rid, year in (("op:facct:2018:pmlr-v28-x13", 2018), ("op:facct:2019:pmlr-v81-one18a", 2019)):
        with pytest.raises(ValidationError, match="PMLR volume"):
            _rec(rid, "FAccT", year)
    assert _rec("op:icml:2013:pmlr-v999-x", "ICML", 2013)  # ICML's rule is unchanged
```

`test_urls.py`: with the same monkeypatch, `urls.native("https://proceedings.mlr.press/v81/one18a.html") == "pmlr-v81-one18a"`. Without it, the result is None while the shipped table lacks v81. `test_scholar_compare.py`: with the monkeypatch, `proceedings_key("https://proceedings.mlr.press/v81/one18a.html") == ("FAccT", 2018, "pmlr-v81-one18a")`. `test_ris.py`: the existing `pmlr_urls(...)` helper, run with a v81 URL and the monkeypatch, still counts `out_of_scope` (mirror `test_an_unparseable_non_icml_pmlr_url_is_out_of_scope`).

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest backend/tests/unit/ingest/test_pmlr.py -q -k "v81 or non_icml or icml_is_untouched or not_paper"`

Expected: FAIL (`unknown columns ['not_papers']`; `only ICML volumes are ingested`).

- [ ] **Step 3: Implement**

`volumes.py`:

```python
PMLR_VENUES: frozenset[str] = frozenset({"ICML", "FAccT"})  # FAccT 2018 (FAT*) is v81 (decision-049, milestone B)
_COLUMNS = {..., "not_papers"}
_KEY = re.compile(r"[A-Za-z0-9_-]+")
```

In `_row`:
- read `not_papers = raw.get("not_papers", [])`, which must be a list of distinct `_KEY` strings ("not_papers …");
- only an ingested row may name them;
- `if papers is not None and len(not_papers) >= papers: raise ValueError(f"{where}: fewer not_papers than papers")`;
- replace the ICML-only check with `if volume.ingested and volume.venue not in PMLR_VENUES: raise ValueError(f"{where}: only ICML and FAccT volumes are ingested from PMLR (spec 01 §Sources)")`;
- add `if volume.ingested and volume.venue != "ICML" and volume.role != "primary": raise ValueError(f"{where}: a non-ICML volume is primary (OpenReview holds none of it)")`;
- `Volume` gains `not_papers: tuple[str, ...] = ()`.

After `ICML_PMLR_VOLUMES`, which is unchanged:

```python
# every ingested volume's (venue, year, track): what a `pmlr-v<N>-<key>` native id names (urls.native, record);
# ICML_PMLR_VOLUMES above stays ICML-only (the RIS importer and scholar_compare's ICML rule read it)
PMLR_NATIVE_VOLUMES: Mapping[int, tuple[str, int, str]] = MappingProxyType(
    {n: (v.venue, v.year, v.track) for n, v in VOLUMES.items() if v.ingested and v.year is not None}
)


def ingested_volume(venue: str, year: int) -> Volume | None:
    return next((v for v in VOLUMES.values() if v.venue == venue and v.ingested and v.year == year), None)


def icml_volume(year: int) -> Volume | None:
    return ingested_volume("ICML", year)
```

`record.py`:
- `PROCEEDINGS_NATIVE["pmlr"]` venues become `frozenset({"ICML", "FAccT"})`.
- In `_consistent`:

```python
            if native.startswith("pmlr-") and self.venue != "ICML":
                number = int(native.split("-", 2)[1][1:])
                if _volumes.PMLR_NATIVE_VOLUMES.get(number, ("", 0, ""))[:2] != (self.venue, self.year):
                    raise ValueError(f"native id {native!r} is not a {self.venue} {self.year} PMLR volume's "
                                     "(pmlr_volumes.toml)")  # fmt: skip
```

Here `from openproceedings.ingest import volumes as _volumes`; `volumes` imports only `vocab`, so there is no cycle.

`pmlr.py`:
- `ingestable`: `if not volume.ingested or volume.venue not in PMLR_VENUES`.
- `mine_volume` uses `volume.venue` in its `ListingReport`. A key in `volume.not_papers` is counted `report.skipped["not_paper"]` before any page fetch, and the key goes into a `named` set.
- After the loop:

```python
    if stale := sorted(set(volume.not_papers) - named):
        raise MinerError(f"PMLR v{number}: not_papers {stale} are not on the index; correct pmlr_volumes.toml",
                         reason="stale_not_paper")  # fmt: skip
    if volume.venue != "ICML" and not report.count_ok:  # ICML keeps its warning (planner decision)
        raise MinerError(f"PMLR v{number}: the index lists {report.listed} entries, the table verified "
                         f"{report.stated}", reason="count_mismatch")  # fmt: skip
```

- `_record` returns `record_from_claims(f"op:{volume.venue.lower()}:{volume.year}:{native}", claims)`.
- The module docstring names FAccT 2018 and the `not_papers` rule.

`urls.native`: `if (q := pmlr(url)) is not None and q[0] in _volumes.PMLR_NATIVE_VOLUMES:`. `scholar_compare.proceedings_key`: `venue, year, _ = PMLR_NATIVE_VOLUMES[volume[0]]; return (venue, year, native)`, read through the module.

`crawl.ingest_pmlr(..., venue: str = "ICML")`: use `volume = ingested_volume(venue, year)`. The error is `f"{venue} {year}: no verified PMLR volume in the volume table …"`, which keeps the "no verified PMLR volume" phrase. In `cli.py`, pmlr's `--venue` passes `venue=ns.venue`.

- [ ] **Step 4: Run the full backend suite and commit**

Run: `uv run pytest backend/tests -q -n auto`. Expected: PASS.

```bash
git add -A backend
git commit -m "feat: PMLR ingests FAccT 2018 (v81) beside ICML: not_papers counted, a non-ICML count mismatch stops, ICML tables untouched"
```

---

### Task 6: The ACM proceedings table, the DOI native rule, Crossref parsing

**Files:**
- Create: `backend/src/openproceedings/ingest/acm_table.py`, `backend/src/openproceedings/ingest/acm_proceedings.toml` (header only; rows arrive in Task 9)
- Create: `backend/src/openproceedings/ingest/sources/crossref.py` (constants, URL builders, parsers, contact)
- Modify: `backend/src/openproceedings/ingest/urls.py` (`acm_doi`, `native`), `eval/scholar_compare.py` (a `doi-` key)
- Create: `backend/tests/unit/ingest/crossref/__init__.py`, `api.py` (builders), `test_acm_table.py`, `test_crossref_parse.py`; Modify: `backend/tests/unit/ingest/test_urls.py`
- Modify: `.env.example` (`CROSSREF_MAILTO=`)

**Interfaces:**
- Produces:
  - `acm_table.VENUES = frozenset({"AIES", "FAccT"})`;
  - `acm_table.Proceedings(venue, year, doi, title, window_from: date, window_until: date, dois: int, verified, source)`, with `.toc` and `.paper(doi) -> bool`;
  - `acm_table.NotPaper(doi, venue, year, kind, reason)`;
  - `acm_table.Table(proceedings: Mapping[tuple[str, int], Proceedings], not_papers: Mapping[str, NotPaper])`, with `.by_toc(toc)` and `.expected(venue, year)`;
  - `acm_table.paper_doi(doi) -> tuple[str, str] | None`, `acm_table.load(text)`, `acm_table.TABLE`;
  - `crossref.SOURCE = "crossref"`, `CACHE_DIR`, `HOST`, `HOSTS`, `MIN_INTERVAL = 1.0`, `ROWS = 1000`, `SELECT`, `MAILTO_ENV = "CROSSREF_MAILTO"`;
  - `crossref.proceedings_url(doi)`, `crossref.work_url(doi)`, `crossref.works_url(row, cursor="*")`;
  - `crossref.Work(doi, type, title, authors, page)`, `crossref.WorksPage(works, next_cursor, total)`;
  - `crossref.parse_works(text)`, `crossref.parse_proceedings(text) -> tuple[str, str, tuple[str, ...]]`;
  - `crossref.clean_title(raw)`, `crossref.title_of(item)`, `crossref.author_name(a)`;
  - `crossref.contact(environ, dotenv) -> str`, `crossref.user_agent(mailto) -> str`;
  - `urls.acm_doi(url) -> str | None`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/unit/ingest/crossref/api.py
"""Crossref REST answers in the shape api.crossref.org serves (checked live 2026-10-10); synthetic text."""

import json
from typing import Any

JSON = {"content-type": "application/json"}
TABLE_TEXT = """
[[proceedings]]
venue = "FAccT"
year = 2023
doi = "10.1145/3593013"
title = "Proceedings of the 2023 ACM Conference on Fairness, Accountability, and Transparency"
window_from = 2023-06-01
window_until = 2023-06-30
dois = 3
verified = 2026-10-10
source = "test"

[[not_paper]]
doi = "10.1145/3593013.3594100"
kind = "tutorial"
reason = "a one-page tutorial abstract"
"""


def work(doi: str, *, title: str | None = "A Paper", subtitle: str | None = None,
         authors: tuple[tuple[str, str], ...] = (("Jane", "Doe"),), type_: str = "proceedings-article",
         page: str | None = "1-10", **extra: Any) -> dict[str, Any]:  # fmt: skip
    item: dict[str, Any] = {"DOI": doi, "type": type_,
                            "author": [{"given": g, "family": f, "sequence": "first" if i == 0 else "additional"}
                                       for i, (g, f) in enumerate(authors)]}  # fmt: skip
    if title is not None:
        item["title"] = [title]
    if subtitle is not None:
        item["subtitle"] = [subtitle]
    if page is not None:
        item["page"] = page
    return item | extra


def works_page(*items: dict[str, Any], cursor: str | None = "c2", total: int | None = None) -> str:
    message = {"facets": {}, "total-results": len(items) if total is None else total, "items": list(items),
               "items-per-page": 1000, "query": {"start-index": 0, "search-terms": None}}  # fmt: skip
    if cursor is not None:
        message["next-cursor"] = cursor
    return json.dumps({"status": "ok", "message-type": "work-list", "message-version": "1.0.0", "message": message})


def proceedings(doi: str = "10.1145/3593013",
                title: str = "Proceedings of the 2023 ACM Conference on Fairness, Accountability, and Transparency",
                isbn: tuple[str, ...] = ("9798400701924",)) -> str:  # fmt: skip
    return json.dumps({"status": "ok", "message-type": "work", "message-version": "1.0.0",
                       "message": {"DOI": doi, "type": "proceedings", "title": [title], "ISBN": list(isbn)}})
```

```python
# backend/tests/unit/ingest/crossref/test_acm_table.py
import pytest
from openproceedings.ingest import acm_table

from tests.unit.ingest.crossref.api import TABLE_TEXT


def test_loads_and_derives_the_expected_records() -> None:
    t = acm_table.load(TABLE_TEXT)
    row = t.proceedings[("FAccT", 2023)]
    assert (row.toc, t.expected("FAccT", 2023)) == ("3593013", 2)  # 3 DOIs, one of them no paper
    assert row.paper("10.1145/3593013.3594011") and not row.paper("10.1145/35930130.1") and not row.paper("10.1145/3593013")
    assert t.by_toc("3593013") is row and t.not_papers["10.1145/3593013.3594100"].year == 2023


@pytest.mark.parametrize(
    ("edit", "message"),
    [(lambda s: s.replace('venue = "FAccT"', 'venue = "ICML"'), "FAccT or AIES"),
     (lambda s: s.replace("year = 2023", "year = 2018"), "doi ids"),
     (lambda s: s.replace('doi = "10.1145/3593013"', 'doi = "10.1145/3593013.1"'), "proceedings DOI"),
     (lambda s: s.replace("window_until = 2023-06-30", "window_until = 2023-05-01"), "window"),
     (lambda s: s.replace("dois = 3", "dois = 1"), "fewer not-paper rows"),
     (lambda s: s.replace('doi = "10.1145/3593013.3594100"', 'doi = "10.1145/9999999.1"'), "no proceedings row"),
     (lambda s: s.replace('kind = "tutorial"', 'kind = "poster"'), "kind"),
     (lambda s: s + s[s.index("[[not_paper]]"):], "listed twice")],
)  # fmt: skip
def test_bad_rows_are_refused(edit, message) -> None:
    with pytest.raises(ValueError, match=message):
        acm_table.load(edit(TABLE_TEXT))


@pytest.mark.parametrize(("doi", "parts"), [("10.1145/3593013.3594011", ("3593013", "3594011")),
    ("10.1145/3593013.3594011a", None), ("10.1145/3593013", None), ("10.1609/aaai.v34i01.1", None)])  # fmt: skip
def test_paper_doi(doi: str, parts) -> None:
    assert acm_table.paper_doi(doi) == parts
```

```python
# backend/tests/unit/ingest/crossref/test_crossref_parse.py
from datetime import UTC, datetime

import pytest
from openproceedings.ingest import acm_table
from openproceedings.ingest.dedup import dedup
from openproceedings.ingest.record import Claim
from openproceedings.ingest.sources import crossref
from openproceedings.ingest.sources.common import CrawlError, record_from_claims

from tests.unit.ingest.crossref import api

T = datetime(2026, 10, 10, tzinfo=UTC)
ROW = acm_table.load(api.TABLE_TEXT).proceedings[("FAccT", 2023)]


def test_a_works_page_and_its_cursor() -> None:
    page = crossref.parse_works(api.works_page(api.work("10.1145/3593013.3594011", title="<i>Fair</i> &amp; Square",
                                                        subtitle="A Study"), cursor="AoJ+/x=", total=1))  # fmt: skip
    (w,) = page.works
    assert (w.doi, w.type, w.title, w.authors, page.next_cursor, page.total) == (
        "10.1145/3593013.3594011", "proceedings-article", "Fair & Square: A Study", ("Jane Doe",), "AoJ+/x=", 1)


@pytest.mark.parametrize(
    ("item", "title"),
    [({"title": ["Fair: A Study"], "subtitle": ["A Study"]}, "Fair: A Study"),  # subtitle already in the title
     ({"title": ["X<sub>1</sub> and <mml:math><mml:mi>k</mml:mi></mml:math>"]}, "X1 and k"),
     ({"title": []}, None), ({}, None), ({"title": ["   "]}, None)],
)  # fmt: skip
def test_title_of(item, title) -> None:
    assert crossref.title_of(item) == title


@pytest.mark.parametrize(
    ("author", "name"),
    [({"given": "Jane", "family": "Doe"}, "Jane Doe"), ({"family": "Doe"}, "Doe"), ({"name": "The Lab"}, "The Lab"),
     ({"given": " Jane ", "family": " van  Doe "}, "Jane van Doe"), ({}, None)],
)  # fmt: skip
def test_author_name(author, name) -> None:
    assert crossref.author_name(author) == name


@pytest.mark.parametrize("text", ["not json", '{"status": "failed", "message": []}', '{"status": "ok"}', ""])
def test_a_page_that_is_not_a_work_list_stops(text: str) -> None:
    with pytest.raises(CrawlError) as e:
        crossref.parse_works(text)
    assert e.value.reason in ("crossref_unreadable", "crossref_error")


def test_the_works_url_is_stable_and_quotes_the_cursor() -> None:
    assert crossref.works_url(ROW) == (
        "https://api.crossref.org/works?filter=prefix:10.1145,from-pub-date:2023-06-01,until-pub-date:2023-06-30"
        f"&rows=1000&select={crossref.SELECT}&cursor=%2A")
    assert crossref.works_url(ROW, "AoJ+/x=").endswith("&cursor=AoJ%2B%2Fx%3D")


def test_the_contact_comes_from_the_environment_or_dotenv_and_is_never_echoed(tmp_path) -> None:
    env = tmp_path / ".env"
    env.write_text("CROSSREF_MAILTO=reviewer@example.org\n")
    assert crossref.contact({}, env) == "reviewer@example.org"
    assert crossref.contact({"CROSSREF_MAILTO": "other@example.org"}, env) == "other@example.org"
    assert crossref.user_agent("reviewer@example.org").endswith("; mailto:reviewer@example.org)")
    with pytest.raises(CrawlError) as e:
        crossref.contact({"CROSSREF_MAILTO": "not an address"}, None)
    assert e.value.reason == "no_contact" and "not an address" not in str(e.value)


def test_a_doi_link_names_the_record_and_passes_dedups_self_naming_check(monkeypatch) -> None:
    monkeypatch.setattr(acm_table, "TABLE", acm_table.load(api.TABLE_TEXT))
    url, where = "https://api.crossref.org/works/10.1145/3593013.3594011", "test"
    claims = [Claim(field=f, value=v, source="crossref", url=url, fetched_at=T, evidence=where) for f, v in (
        ("venue", "FAccT"), ("year", 2023), ("track", "main"), ("status", "accepted"), ("title", "A Paper"),
        ("urls.doi", "10.1145/3593013.3594011"), ("urls.proceedings", "https://doi.org/10.1145/3593013.3594011"))]
    record = record_from_claims("op:facct:2023:doi-3593013.3594011", claims)
    assert dedup([record]).records == (record,)
```

`test_urls.py`:

```python
@pytest.fixture
def acm(monkeypatch):
    monkeypatch.setattr(acm_table, "TABLE", acm_table.load(api.TABLE_TEXT))


@pytest.mark.parametrize("url", ["https://doi.org/10.1145/3593013.3594011", "http://dx.doi.org/10.1145/3593013.3594011",
    "https://DOI.org/10.1145/3593013.3594011", "https://doi.org/10.1145%2F3593013.3594011",
    "https://doi.org/10.1145/3593013.3594011?ref=x"])  # fmt: skip
def test_a_listed_acm_paper_doi_link_names_its_doi_id(acm, url: str) -> None:
    assert urls.native(url) == "doi-3593013.3594011"


@pytest.mark.parametrize("url", ["https://doi.org/10.1145/3593013.3594011a", "https://doi.org/10.1145/3593013.3594011/x",
    "https://doi.org/10.1145/3593013.359%204011", "https://doi.org/10.1145/3593013.3594011%0A",
    "https://doi.org/10.1145/9999999.1", "https://doi.org/10.1145/3593013", "https://dl.acm.org/doi/10.1145/3593013.3594011",
    "https://example.org/10.1145/3593013.3594011"])  # fmt: skip
def test_a_link_that_is_not_a_listed_acm_paper_names_nothing(acm, url: str) -> None:
    assert urls.native(url) is None
```

`test_scholar_compare.py`: with the same fixture, `proceedings_key("https://doi.org/10.1145/3593013.3594011") == ("FAccT", 2023, "doi-3593013.3594011")`.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest backend/tests/unit/ingest/crossref backend/tests/unit/ingest/test_urls.py -q`. Expected: FAIL (`ModuleNotFoundError: acm_table`).

- [ ] **Step 3: Implement `acm_table.py`**

Use `ojs_table.py`'s style. Docstring: the table's purpose, the window rule, that `dois` counts every DOI extending the proceedings DOI in the window (not-paper rows included), and that a `[[not_paper]]` DOI is counted, never a record.

```python
VENUES: frozenset[str] = frozenset({"AIES", "FAccT"})
_TOC = re.compile(r"10\.1145/[0-9]+")
_PAPER = re.compile(r"10\.1145/([0-9]+)\.([0-9]+)")
NOT_PAPER_KINDS = frozenset({"tutorial", "craft session", "keynote", "panel", "front matter"})
_PROCEEDINGS = {"venue", "year", "doi", "title", "window_from", "window_until", "dois", "verified", "source"}
_NOT_PAPER = {"doi", "kind", "reason"}


def paper_doi(doi: str) -> tuple[str, str] | None:
    """(toc, n) of an ACM paper DOI `10.1145/<toc>.<n>` (digits only, compared lower-case), else None."""
    m = _PAPER.fullmatch(doi.strip().lower())
    return (m.group(1), m.group(2)) if m else None
```

`load` validates each `[[proceedings]]` row:
- venue in `VENUES` ("FAccT or AIES");
- `venue_name(venue, year)` holds and `year in record.DOI_YEARS[venue]` ("doi ids …");
- doi matches `_TOC` ("proceedings DOI");
- `window_from <= window_until`, both dates ("window");
- `dois` a positive int;
- (venue, year) and doi each unique.

Each `[[not_paper]]` row: the DOI passes `paper_doi` and its toc is a proceedings row ("no proceedings row"); the kind is in `NOT_PAPER_KINDS`; the reason is non-empty; each DOI appears once ("listed twice"). The row's venue and year are taken from its proceedings row. Per proceedings, the not-paper rows must be fewer than `dois` ("fewer not-paper rows"). `Proceedings.paper(doi)` is `doi.strip().lower().startswith(self.doi + ".")`.

```python
TABLE: Table = load(files("openproceedings.ingest").joinpath("acm_proceedings.toml").read_text(encoding="utf-8"))
```

The header of `acm_proceedings.toml` documents every column, in the house style.

- [ ] **Step 4: Implement the DOI rule** (`urls.py`)

```python
from urllib.parse import unquote

from openproceedings.ingest import acm_table

_DOI_HOSTS = frozenset({"doi.org", "dx.doi.org"})


def acm_doi(url: str) -> str | None:
    """The ACM paper DOI a doi.org link names (`10.1145/<toc>.<n>`, lower-case), when its proceedings are a row of
    acm_proceedings.toml (FAccT, AIES; decision-049), else None. Only doi.org: the DOI is the paper's name."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or parsed.netloc.lower() not in _DOI_HOSTS:
        return None
    doi = unquote(parsed.path.removeprefix("/")).lower()
    parts = acm_table.paper_doi(doi)
    if parts is None or acm_table.TABLE.by_toc(parts[0]) is None:
        return None
    return doi
```

`paper_doi` refuses `"…%0A"` once unquoted (it uses `fullmatch` on digits, and its `strip()` must not hide a trailing newline). Use `doi != doi.strip()` → None before matching, and add that guard in `acm_doi` as well. In `native()`: `if (doi := acm_doi(url)) is not None: return "doi-" + doi.split("/", 1)[1]`.

In `scholar_compare.proceedings_key`, allow the `"doi-"` prefix:

```python
    if native.startswith("doi-"):
        toc = native.removeprefix("doi-").split(".", 1)[0]
        row = acm_table.TABLE.by_toc(toc)
        return None if row is None else (row.venue, row.year, native)
```

- [ ] **Step 5: Implement the parsers** (`sources/crossref.py`)

The module docstring covers:
- the route: the proceedings record, then `/works` paged by cursor, filtered by `prefix:10.1145` and the table's window, keeping DOIs that extend `10.1145/<toc>.`;
- sequential requests with the `mailto` User-Agent (parallel requests get 429);
- the cursor rule (Task 7);
- the fields: no abstracts, which `select` leaves out.

Code:

```python
SOURCE: Source = "crossref"
CACHE_DIR = "crossref"  # <data>/cache/crossref
HOST = "api.crossref.org"
HOSTS = frozenset({HOST})
MIN_INTERVAL = 1.0  # one request at a time, a second apart: parallel requests get HTTP 429 (checked 2026-10-09)
ROWS = 1000  # Crossref's page maximum
SELECT = "DOI,title,subtitle,author,type,page,published"  # never `abstract` (design: official sources only)
MAILTO_ENV = "CROSSREF_MAILTO"
_EMAIL = re.compile(r"[^@\s<>()\"';,]+@[^@\s<>()\"';,]+\.[A-Za-z]{2,}")
_TAG = re.compile(r"<[^<>]*>")


def proceedings_url(doi: str) -> str:
    return f"https://{HOST}/works/{doi}"


work_url = proceedings_url  # a work's own API URL: every claim's url (stable, unlike a cursor page)


def works_url(row: Proceedings, cursor: str = "*") -> str:
    return (f"https://{HOST}/works?filter=prefix:10.1145,from-pub-date:{row.window_from.isoformat()},"
            f"until-pub-date:{row.window_until.isoformat()}&rows={ROWS}&select={SELECT}&cursor={quote(cursor, safe='')}")  # fmt: skip


def clean_title(raw: str) -> str:
    """Crossref's title text: JATS/HTML/MathML tags dropped (their text kept), entities unescaped, whitespace
    collapsed. `title_text` then replaces control characters as for every source."""
    return " ".join(html.unescape(_TAG.sub("", raw)).split())


def title_of(item: Mapping[str, Any]) -> str | None:
    titles = [clean_title(t) for t in item.get("title") or [] if isinstance(t, str)]
    title = next((t for t in titles if t), None)
    if title is None:
        return None
    sub = next((s for s in (clean_title(x) for x in item.get("subtitle") or [] if isinstance(x, str)) if s), None)
    return f"{title}: {sub}" if sub and sub.casefold() not in title.casefold() else title


def author_name(a: Mapping[str, Any]) -> str | None:
    parts = [" ".join(str(a.get(k) or "").split()) for k in ("given", "family")]
    joined = " ".join(p for p in parts if p)
    return joined or (" ".join(str(a.get("name") or "").split()) or None)
```

`_message(text, kind)` handles errors:
- `json.loads` failing raises `crossref_unreadable`;
- a non-dict raises `crossref_unreadable`;
- `status != "ok"` raises `crossref_error` (the message names the status, never the body);
- `message-type != kind` or no dict `message` raises `crossref_unreadable`.

`parse_works` builds `Work(doi=str(item["DOI"]).strip().lower(), type=str(item.get("type", "")), title=title_of(item), authors=tuple(n for a in item.get("author") or [] if isinstance(a, dict) and (n := author_name(a))), page=item.get("page"))`. Items with no DOI raise `crossref_unreadable`. `total = int(message["total-results"])` and `next_cursor = message.get("next-cursor") or None`.

`parse_proceedings` checks `message-type == "work"` and `type == "proceedings"`, and returns `(DOI lower, title_of or "", tuple(ISBN))`.

```python
def contact(environ: Mapping[str, str], dotenv: Path | None) -> str:
    """The address Crossref's polite pool asks for, from `CROSSREF_MAILTO` (the environment first, then `.env`); it
    goes into the User-Agent only, never a URL, a cache entry, a claim or a log line."""
    values = {**(read_dotenv(dotenv) if dotenv else {}), **environ}
    value = values.get(MAILTO_ENV, "").strip()
    if not _EMAIL.fullmatch(value):
        raise CrawlError(f"a live Crossref crawl needs {MAILTO_ENV} (an e-mail address) in the environment or .env",
                         reason="no_contact")  # fmt: skip
    return value


def user_agent(mailto: str) -> str:
    return f"{USER_AGENT.removesuffix(')')}; mailto:{mailto})"
```

`read_dotenv` and `repo_dotenv` come from `openreview_client`.

Add `CROSSREF_MAILTO=` to `.env.example`, with a comment line: `# an e-mail address for Crossref's polite pool (op ingest crossref); never committed`.

- [ ] **Step 6: Run the full backend suite and commit**

Run: `uv run pytest backend/tests -q -n auto`. Expected: PASS.

```bash
git add -A backend .env.example
git commit -m "feat: the ACM proceedings table, doi-<toc>.<n> ids named by doi.org links, Crossref page parsing and contact"
```

---

### Task 7: Crossref harvest, records, `op ingest crossref`, replay

**Files:**
- Modify: `backend/src/openproceedings/ingest/sources/crossref.py` (`CrossrefReport`, `ProceedingsResult`, `harvest`, `mine_proceedings`, `_record`)
- Modify: `backend/src/openproceedings/ingest/sources/crawl.py` (`crossref_fetcher`, `ingest_crossref`, `CROSSREF`, `SOURCES`)
- Modify: `backend/src/openproceedings/cli.py` (the `crossref` parser, `_ingest_crossref`)
- Create: `backend/tests/unit/ingest/crossref/test_crossref_mine.py`, `test_crossref_crawl.py`; Modify: `backend/tests/unit/test_cli.py`, `backend/tests/unit/ingest/test_snapshot.py`, `backend/tests/unit/ingest/ojs/test_ojs_crawl.py` (the order test becomes `crawl.SOURCES[-2:] == (crawl.DBLP_AAAI, crawl.CROSSREF)`)

**Interfaces:**
- Consumes: Task 6.
- Produces:
  - `crossref.CrossrefReport(ListingReport)` with `window_works`, `pages`, `no_authors`;
  - `crossref.ProceedingsResult(records, reports)`;
  - `crossref.mine_proceedings(venue, year, fetcher, *, refresh=False, table=None) -> ProceedingsResult`;
  - `crawl.crossref_fetcher(cache, *, offline, transport=None, min_interval=DEFAULT_INTERVAL, mailto=None)`;
  - `crawl.ingest_crossref(keys, cache, *, offline=False, dry_run=False, refresh=False, transport=None, min_interval=…, table=None, mailto=None)`;
  - `crawl.CROSSREF`, keyed `(venue, year)`, with markers `<cache>/crossref/crawls/<venue>-<year>.json` = `{"source": "crossref", "venue": V, "year": Y}`;
  - CLI `op ingest crossref`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/unit/ingest/crossref/test_crossref_mine.py
from pathlib import Path

import pytest
from openproceedings.ingest import acm_table
from openproceedings.ingest.dedup import attribution, dedup
from openproceedings.ingest.sources import crossref
from openproceedings.ingest.sources.common import CrawlError
from openproceedings.ingest.sources.http import canonical

from tests.unit.ingest.crossref import api
from tests.unit.ingest.proceedings_helpers import FakeTransport, fetcher, response, seed

TABLE = acm_table.load(api.TABLE_TEXT)
ROW = TABLE.proceedings[("FAccT", 2023)]
D1, D2, NP = "10.1145/3593013.3594011", "10.1145/3593013.3594012", "10.1145/3593013.3594100"
FOREIGN = "10.1145/3600000.3600001"


@pytest.fixture(autouse=True)
def _acm(monkeypatch):
    monkeypatch.setattr(acm_table, "TABLE", TABLE)  # urls.native reads it: records must name themselves


def _seed_chain(cache: Path, *pages: str, head: str | None = None) -> None:
    """Seed the proceedings record and a cursor chain: page i's next cursor is `c<i+1>`, read by page i+1's URL."""
    seed(cache, "crossref", crossref.proceedings_url(ROW.doi), head or api.proceedings(), keep_query=True)
    for i, text in enumerate(pages):
        seed(cache, "crossref", crossref.works_url(ROW, "*" if i == 0 else f"c{i + 1}"), text, keep_query=True)


def _offline(cache: Path):
    f, _ = fetcher(cache / "crossref", None, crossref.HOSTS, accept="application/json", expect="json", keep_query=True)
    return f


def _whole(cache: Path, *items, total: int = 5) -> None:
    _seed_chain(cache, api.works_page(*items[:2], cursor="c2", total=total),
                api.works_page(*items[2:], cursor="c3", total=total), api.works_page(cursor="c4", total=total))


def test_a_chain_becomes_records_foreign_dois_dropped_not_paper_counted(tmp_path: Path) -> None:
    _whole(tmp_path, api.work(D1, authors=(("Jane", "Doe"), ("Ada", "Lovelace"))), api.work(FOREIGN),
           api.work(D2), api.work(NP, title="Tutorial: Synthetic"), api.work("10.1145/3600000.3600002"))
    result = crossref.mine_proceedings("FAccT", 2023, _offline(tmp_path), table=TABLE)
    by = {r.native: r for r in result.records}
    assert set(by) == {"doi-3593013.3594011", "doi-3593013.3594012"}
    r = by["doi-3593013.3594011"]
    assert (r.id, r.venue, r.year, r.track, r.status, r.abstract) == (
        "op:facct:2023:doi-3593013.3594011", "FAccT", 2023, "main", "accepted", None)
    assert r.authors == ("Jane Doe", "Ada Lovelace") and r.urls.doi == D1
    assert r.urls.proceedings == f"https://doi.org/{D1}"
    assert {c.url for c in r.provenance} == {f"https://api.crossref.org/works/{D1}"}  # never a cursor page
    (report,) = result.reports
    assert (report.stated, report.listed, report.records, report.window_works, report.pages, report.count_ok) == (
        3, 3, 2, 5, 3, True)
    assert report.skipped == {"not_paper": 1}
    assert len(dedup(result.records).records) == 2


def test_an_abstract_from_crossref_would_be_credited_to_the_doi_link() -> None:
    from openproceedings.ingest.record import Claim
    from tests.unit.ingest.crossref.test_crossref_parse import T
    claim = Claim(field="abstract", value="T", source="crossref", url=f"https://api.crossref.org/works/{D1}", fetched_at=T)
    got = attribution("T", [claim], forum=None, proceedings=f"https://doi.org/{D1}", native="doi-3593013.3594011")
    assert got.url == f"https://doi.org/{D1}"


@pytest.mark.parametrize(("bad", "reason"), [("10.1145/3593013.3594011a", "odd_doi"), ("10.1145/3593013.x", "odd_doi")])
def test_an_odd_doi_under_the_proceedings_stops(tmp_path: Path, bad: str, reason: str) -> None:
    _whole(tmp_path, api.work(D1), api.work(bad), api.work(NP), total=3)
    with pytest.raises(CrawlError, match=bad) as e:
        crossref.mine_proceedings("FAccT", 2023, _offline(tmp_path), table=TABLE)
    assert e.value.reason == reason


def test_a_count_that_differs_from_the_table_stops(tmp_path: Path) -> None:
    _whole(tmp_path, api.work(D1), api.work(NP), total=2)
    with pytest.raises(CrawlError, match="2.*3|3.*2") as e:
        crossref.mine_proceedings("FAccT", 2023, _offline(tmp_path), table=TABLE)
    assert e.value.reason == "count_mismatch"


def test_a_not_paper_row_the_harvest_lacks_stops(tmp_path: Path) -> None:
    _whole(tmp_path, api.work(D1), api.work(D2), api.work("10.1145/3593013.3594013"), total=3)
    with pytest.raises(CrawlError, match=NP) as e:
        crossref.mine_proceedings("FAccT", 2023, _offline(tmp_path), table=TABLE)
    assert e.value.reason == "stale_not_paper"


def test_a_work_with_no_title_stops_unless_a_not_paper_row_names_it(tmp_path: Path) -> None:
    _whole(tmp_path, api.work(D1), api.work(D2, title=None), api.work(NP, title=None), total=3)
    with pytest.raises(CrawlError, match=D2) as e:  # NP has no title either, and is fine: it is no paper
        crossref.mine_proceedings("FAccT", 2023, _offline(tmp_path), table=TABLE)
    assert e.value.reason == "no_title"


def test_a_work_with_no_authors_is_kept_and_counted(tmp_path: Path) -> None:
    _whole(tmp_path, api.work(D1, authors=()), api.work(D2), api.work(NP), total=3)
    result = crossref.mine_proceedings("FAccT", 2023, _offline(tmp_path), table=TABLE)
    assert next(r for r in result.records if r.urls.doi == D1).authors == ()
    assert result.reports[0].no_authors == 1


def test_a_total_that_moves_mid_chain_stops(tmp_path: Path) -> None:
    _seed_chain(tmp_path, api.works_page(api.work(D1), cursor="c2", total=3),
                api.works_page(api.work(D2), api.work(NP), cursor="c3", total=4), api.works_page(cursor="c4", total=4))
    with pytest.raises(CrawlError) as e:
        crossref.mine_proceedings("FAccT", 2023, _offline(tmp_path), table=TABLE)
    assert e.value.reason == "listing_changed"


def test_a_proceedings_record_that_is_not_the_tables_stops(tmp_path: Path) -> None:
    _whole(tmp_path, api.work(D1), api.work(D2), api.work(NP), total=3)
    seed(tmp_path, "crossref", crossref.proceedings_url(ROW.doi), api.proceedings(title="Another Conference"), keep_query=True)
    with pytest.raises(CrawlError) as e:
        crossref.mine_proceedings("FAccT", 2023, _offline(tmp_path), table=TABLE)
    assert e.value.reason == "proceedings_mismatch"


def _script(t: FakeTransport, url: str, text: str) -> None:
    t.script[canonical(url, keep_query=True)] = [response(text, headers=api.JSON)]


def test_a_resumed_crawl_whose_chain_is_not_whole_starts_again_from_cursor_star(tmp_path: Path) -> None:
    # run 1 cached the first page (cursor "stale") and stopped; by run 2 that cursor has expired
    _seed_chain(tmp_path, api.works_page(api.work(D1), cursor="stale", total=3))
    t = FakeTransport({})
    _script(t, crossref.works_url(ROW), api.works_page(api.work(D1), cursor="fresh", total=3))
    _script(t, crossref.works_url(ROW, "fresh"), api.works_page(api.work(D2), api.work(NP), cursor="end", total=3))
    _script(t, crossref.works_url(ROW, "end"), api.works_page(cursor="end2", total=3))
    live, _ = fetcher(tmp_path / "crossref", t, crossref.HOSTS, min_interval=0.0, accept="application/json",
                      expect="json", keep_query=True, user_agent="ua")  # fmt: skip
    result = crossref.mine_proceedings("FAccT", 2023, live, table=TABLE)
    assert canonical(crossref.works_url(ROW, "stale"), keep_query=True) not in t.calls  # the dead cursor is never sent
    assert len(result.records) == 2


def test_the_replay_follows_the_cached_chain_offline(tmp_path: Path) -> None:
    test_a_resumed_crawl_whose_chain_is_not_whole_starts_again_from_cursor_star(tmp_path)
    again = crossref.mine_proceedings("FAccT", 2023, _offline(tmp_path), table=TABLE)
    assert sorted(r.id for r in again.records) == ["op:facct:2023:doi-3593013.3594011", "op:facct:2023:doi-3593013.3594012"]


def test_an_offline_run_without_the_chain_is_refused(tmp_path: Path) -> None:
    seed(tmp_path, "crossref", crossref.proceedings_url(ROW.doi), api.proceedings(), keep_query=True)
    with pytest.raises(CrawlError) as e:
        crossref.mine_proceedings("FAccT", 2023, _offline(tmp_path), table=TABLE)
    assert e.value.reason == "not_cached"
```

```python
# backend/tests/unit/ingest/crossref/test_crossref_crawl.py
import json
import logging

from openproceedings.ingest import acm_table
from openproceedings.ingest.sources import crawl, crossref

from tests.unit.ingest.crossref.test_crossref_mine import D1, D2, NP, ROW, TABLE, _script, _whole
from tests.unit.ingest.crossref import api
from tests.unit.ingest.proceedings_helpers import FakeTransport


def test_offline_ingest_marks_the_proceedings_and_the_replay_rebuilds_them(tmp_path, monkeypatch) -> None:
    _whole(tmp_path, api.work(D1), api.work(D2), api.work(NP), total=3)
    out = crawl.ingest_crossref([("FAccT", 2023)], tmp_path, offline=True, table=TABLE)
    assert [x["records"] for x in out["listings"]] == [2]
    assert json.loads((tmp_path / "crossref" / "crawls" / "FAccT-2023.json").read_text()) == {
        "source": "crossref", "venue": "FAccT", "year": 2023}
    (replayed,) = crawl.CROSSREF.replay(tmp_path)  # acm_table.TABLE is monkeypatched by the autouse fixture's module
    assert len(replayed.records) == 2


def test_a_live_crawl_sends_the_contact_in_the_user_agent_and_nowhere_else(tmp_path, caplog) -> None:
    t = FakeTransport({})
    _script(t, crossref.proceedings_url(ROW.doi), api.proceedings())
    _script(t, crossref.works_url(ROW), api.works_page(api.work(D1), api.work(D2), api.work(NP), cursor="c2", total=3))
    _script(t, crossref.works_url(ROW, "c2"), api.works_page(cursor="c3", total=3))
    caplog.set_level(logging.DEBUG)
    crawl.ingest_crossref([("FAccT", 2023)], tmp_path, transport=t, min_interval=0, table=TABLE,
                          mailto="reviewer@example.org")  # fmt: skip
    assert "reviewer@example.org" not in caplog.text
    assert all("reviewer@example.org" not in p.read_text() for p in tmp_path.rglob("*.json"))


def test_a_proceedings_the_table_lacks_is_refused(tmp_path) -> None:
    import pytest
    with pytest.raises(crawl.MinerError, match="AIES 2019"):
        crawl.ingest_crossref([("AIES", 2019)], tmp_path, offline=True, table=TABLE)


def test_crossref_is_replayed_last() -> None:
    assert crawl.SOURCES[-2:] == (crawl.DBLP_AAAI, crawl.CROSSREF)
```

(The `_acm` fixture in `test_crossref_mine.py` is autouse for that module only. In `test_crossref_crawl.py`, add `monkeypatch.setattr(acm_table, "TABLE", TABLE)` to each test, or a module-level autouse fixture.)

In `test_cli.py`, mirroring the ojs test:
- `op ingest crossref --venue FAccT --year 2023 --offline` dispatches to `ingest_crossref([("FAccT", 2023)], …, offline=True)`;
- `op ingest crossref --venue ICML` exits 2 (`invalid choice`);
- `op ingest crossref --year 2017` exits 2 (`no acm_proceedings.toml row`).

In `test_snapshot.py`, following the file's PMLR/dblp/ojs pattern: seed the chain and the marker, build, and assert the two `op:facct:2023:doi-*` records and `sources["crossref"]["listings"][0]["count_ok"] is True`.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest backend/tests/unit/ingest/crossref -q`. Expected: FAIL (`AttributeError: mine_proceedings`).

- [ ] **Step 3: Implement the miner** (append to `crossref.py`)

```python
@dataclass(kw_only=False)
class CrossrefReport(ListingReport):
    """One ACM proceedings from Crossref: the shared listing counts, plus the works the window returned (every
    prefix:10.1145 DOI, this proceedings' and others'), the cursor pages read, and the records with no author."""

    window_works: int = 0
    pages: int = 0
    no_authors: int = 0

    def to_manifest(self) -> dict[str, Any]:
        out = super().to_manifest() | {"window_works": self.window_works, "pages": self.pages,
                                       "no_authors": self.no_authors}  # fmt: skip
        return dict(sorted(out.items()))


@dataclass
class ProceedingsResult:
    records: list[PaperRecord]
    reports: list[CrossrefReport]


Get = Callable[[str, bool], Page | None]


def _walk(row: Proceedings, get: Get) -> list[tuple[Page, WorksPage]] | None:
    """The cursor chain from `cursor=*` to its first empty page, through `get` (None: a page `get` can't give)."""
    out: list[tuple[Page, WorksPage]] = []
    cursor, total = "*", None
    while True:
        page = get(works_url(row, cursor), cursor == "*")
        if page is None:
            return None
        if not page.ok:
            raise CrawlError(f"{page.url} answered HTTP {page.status}", reason="no_listing")
        parsed = parse_works(page.text)
        if total is None:
            total = parsed.total
        elif parsed.total != total:
            raise CrawlError(f"Crossref {row.venue} {row.year}: total-results moved from {total} to {parsed.total} "
                             "mid-chain; re-run with --refresh", reason="listing_changed")  # fmt: skip
        out.append((page, parsed))
        if not parsed.works or parsed.next_cursor is None:
            return out
        if len(out) > total // ROWS + 1:
            raise CrawlError(f"Crossref {row.venue} {row.year}: the cursor chain runs past {total} results",
                             reason="listing_changed")  # fmt: skip
        cursor = parsed.next_cursor


def harvest(row: Proceedings, fetcher: Fetcher, *, refresh: bool = False) -> list[tuple[Page, WorksPage]]:
    """The chain the cache holds whole (the replay's route), else, live, a fresh chain from `cursor=*` with its first
    page fetched again: a cursor expires within minutes, so a half-cached chain can't be resumed."""
    chain = None if refresh else _walk(row, lambda url, _first: fetcher.get(url) if fetcher.is_cached(url) else None)
    if chain is not None:
        return chain
    if fetcher.offline:
        raise CrawlError(f"Crossref {row.venue} {row.year}: the cursor chain is not in the cache; run op ingest "
                         "crossref", reason="not_cached")  # fmt: skip
    fresh = _walk(row, lambda url, first: fetcher.get(url, refresh=first))
    assert fresh is not None  # a live get always gives a page
    return fresh
```

`mine_proceedings(venue, year, fetcher, *, refresh=False, table=None)`:
- `table = table or acm_table.TABLE`. Its row is required (`unlisted_proceedings`).
- Read `head = fetcher.get(proceedings_url(row.doi), refresh=refresh)`. Not OK raises `no_listing`. Then `doi, title, _isbn = parse_proceedings(head.text)`; a DOI other than `row.doi`, or a title not starting with `row.title`, raises `proceedings_mismatch`, naming both titles.
- `chain = harvest(...)`.
- `report = CrossrefReport(SOURCE, venue, year, proceedings_url(row.doi), "primary", row.dois, pages=len(chain))`. Append `head.fetched_at` and every page's fetch time to `report.fetched`.
- Walk the works:
  - count each in `window_works`;
  - skip any that is not `row.paper(w.doi)`;
  - `acm_table.paper_doi(w.doi) is None` raises `odd_doi`: `"Crossref {venue} {year}: DOI {w.doi!r} extends {row.doi} but is not {row.doi}.<digits>: check it before it is indexed"`;
  - a DOI already seen with an equal `Work` is counted `duplicate`; a different `Work` raises `conflicting_duplicate`;
  - anything else is kept in `seen[w.doi] = (page, w)` and counted in `report.listed`.
- If `report.listed != row.dois`, raise `count_mismatch`: `"Crossref {venue} {year}: {listed} DOIs extend {row.doi} in the window, the table verified {row.dois}: check the window and the table"`.
- `stale = sorted(np.doi for np in table.not_papers.values() if row.paper(np.doi) and np.doi not in seen)` raises `stale_not_paper`.
- In DOI order:
  - a not-paper DOI is counted `not_paper`;
  - no title raises `no_title`: `f"Crossref {venue} {year}: {doi} has no title: name it in acm_proceedings.toml [[not_paper]] if it is no paper, else check Crossref"`;
  - otherwise build `record = _record(row, w, page)` (a `ValidationError` or `ValueError` raises `invalid_record`, naming the DOI and the error type), add `report.no_authors += not record.authors`, and call `report.count(record, "no_abstract")`.
- Log `crossref_proceedings_mined` (venue, year, listed, records, window_works, pages, ms). A non-zero `no_authors` gets a `listing_attention` warning.

`_record(row, w, page)`:
- `where = f"Crossref work {w.doi} in proceedings {row.doi} (acm_proceedings.toml {row.venue} {row.year})"`;
- claims at `work_url(w.doi)` and `page.fetched_at`;
- `venue`; `year`; `track` `"main"` (`f"{where}: every paper of the proceedings is main (decision-049)"`); `status` `"accepted"` (`f"published in {row.doi}"`);
- `title` via `title_text` with `title_evidence`; `authors` when there are any (`f"{where}: author, in Crossref's order"`);
- `urls.doi` = `w.doi`; `urls.proceedings` = `f"https://doi.org/{w.doi}"`;
- returns `record_from_claims(f"op:{row.venue.lower()}:{row.year}:doi-{w.doi.split('/', 1)[1]}", claims)`.

- [ ] **Step 4: Implement crawl and CLI**

```python
def crossref_fetcher(cache: Path, *, offline: bool, transport: Transport | None = None,
                     min_interval: float = DEFAULT_INTERVAL, mailto: str | None = None) -> Fetcher:  # fmt: skip
    live = None if offline else (transport or urllib_transport)
    agent = None if offline else crossref.user_agent(mailto or crossref.contact(os.environ, repo_dotenv()))
    return Fetcher(PageCache(cache / crossref.CACHE_DIR), live, hosts=crossref.HOSTS,
                   min_interval=max(min_interval, crossref.MIN_INTERVAL), accept="application/json", expect="json",
                   keep_query=True, user_agent=agent)  # fmt: skip
```

`ingest_crossref(keys, cache, …)`:
- `table = table or acm_table.TABLE`; `wanted = sorted(set(keys)) or sorted(table.proceedings)`.
- An unknown key raises `MinerError(f"{v} {y}: no acm_proceedings.toml row", reason="unlisted_proceedings")`.
- A dry run builds an **offline** fetcher and returns `{"dry_run": True, "proceedings": [{"venue", "year", "record_cached", "first_page_cached"}], …}` with no network and no contact.
- Otherwise `CROSSREF.ingest(cache, wanted, lambda k: crossref.mine_proceedings(*k, f, refresh=refresh, table=table), lambda k, _: (f"{k[0]}-{k[1]}", {"source": crossref.SOURCE, "venue": k[0], "year": k[1]}))`.
- Log `crossref_ingested` (proceedings, listings, requests).
- Return `_output(...)`.

```python
CROSSREF: Crawls[crossref.ProceedingsResult] = Crawls(
    lambda cache: crawls_dir(cache, crossref.CACHE_DIR), lambda m: (str(m["venue"]), int(m["year"])),
    lambda k: f"Crossref {k[0]} {k[1]}", "op ingest crossref",
    lambda cache, k: crossref.mine_proceedings(k[0], k[1], crossref_fetcher(cache, offline=True)),
)  # fmt: skip
SOURCES = (openreview_v2.CRAWLS, openreview_v1.CRAWLS, ICLR, NEURIPS, PMLR, DBLP, OJS, DBLP_AAAI, CROSSREF)
```

In `cli.py`:
- Add `crossref` to the `ingest` help.
- The `crossref` sub-parser takes `--venue` (`dest="venues"`, `action="append"`, `choices=sorted(acm_table.VENUES)`), `--year` (`dest="years"`, `action="append"`, `type=_years`) and the OJS flag block.
- `_ingest_crossref` checks `--delay` as `_ingest_ojs` does. It refuses `--dry-run` with `--offline`. It builds `keys = [k for k in sorted(table.proceedings) if (not ns.venues or k[0] in ns.venues) and (not years or k[1] in years)]`. Explicit filters that match nothing raise `_usage("no acm_proceedings.toml row matches …")`. Then it prints `ingest_crossref(keys, …)`.
- A missing contact surfaces as `CrawlError` `no_contact` through `cli.main`'s one handler.

- [ ] **Step 5: Run the full backend suite and commit**

Run: `uv run pytest backend/tests -q -n auto` and `make lint`. Expected: PASS.

```bash
git add -A backend
git commit -m "feat: op ingest crossref (FAccT, AIES): the cursor chain restarts when stale, counts and not-paper rows stop, replay offline"
```

---

### Task 8: Census A: the dblp AAAI rows from the pinned release (local, no network)

The controller runs this. It reads the release already on disk; it fetches nothing. Data dir: `OP=/Users/jeevanparmar/school/Research/Ferguson/openproceedings/data`.

**Files:**
- Create: `scripts/dblp_aaai_census.py` (read-only helper)
- Modify: `backend/src/openproceedings/ingest/dblp_aaai.toml` (every row)
- Modify: `backend/tests/unit/ingest/test_dblp_aaai_table.py` (pin the shipped table)
- Modify: `docs/research/2026-10-09-aaai-aies-facct-iaseai-sources.md` (§AAAI 1980–2008)

- [ ] **Step 1: Record ICML's extract hash** (it must not change):

```bash
shasum -a 256 "$OP/cache/dblp/extract/20e45961bec5610dc07b8e932ccd27a2387534cfa12c92a24289fe873aebe969.json"
```

- [ ] **Step 2: Write `scripts/dblp_aaai_census.py`.** It takes `--cache <dir>` and does the following:
  - Calls `dblp.prepare_slices(cache, None, slices=(dblp.AAAI_SLICE,))` (offline: release on disk; this writes AAAI's extract only).
  - Prints, for every `conf/aaai/` proceedings entry dated 1980–2009: the key, the year, dblp's title and the number of inproceedings crossref'ing it.
  - Lists the years 1980–2009 with no proceedings key (they must be exactly 1981, 1985, 1989, 2001, 2003 and 2009).
  - Proposes the not-paper candidates: entries under main or workshop keys whose titles match `(?i)^(invited talk|keynote|panel|preface|front matter|index|proceedings|program committee)` or have no author.
  - Counts authors that carry a homonym number, keys that fail `dblp.NATIVE`, `publtype` entries and DOI `ee`s.
  - Prints draft TOML rows.

  It writes nothing but the extract.

- [ ] **Step 3: Run it and cross-check IAAI**:

```bash
uv run python scripts/dblp_aaai_census.py --cache "$OP/cache" | tee "$TMPDIR/aaai-census.txt"
gzip -dc "$OP/cache/dblp/release/dblp-2026-10-03.xml.gz" | grep -o '<crossref>conf/aaai/[^<]*</crossref>' | sort | uniq -c
```

  Compare the second count per key with the census's `conf/aaai/`-keyed counts. The difference is records keyed outside `conf/aaai/` (`conf/iaai/…`) that crossref an AAAI volume. Record that difference per year in the research note, as excluded by design (IAAI before 2010 is out of scope).

- [ ] **Step 4: Write the rows.**
  - One `[[year]]` per held year, with every main key. The split years 1986, 1991, 1994 and 1996 have two keys.
  - A `[[workshop]]` for each workshop key dated 1980–2008, if there are any.
  - An `[[excluded]]` for any other key, with a reason.
  - A `[[not_paper]]` for each candidate the controller confirms, with kind and reason. Unconfirmed candidates stay papers, and the note lists them for owner review.
  - Re-run until `op ingest dblp --venue AAAI --year 1980-2008` (Task 12's command, here with `OP_DATA_DIR="$OP"`) prints every listing `count_ok: true` and `not_held: [1981, 1985, 1989, 2001, 2003]`.
  - Confirm Step 1's hash is unchanged.

- [ ] **Step 5: Pin the shipped table** (append to `test_dblp_aaai_table.py`):

```python
def test_the_shipped_table_covers_every_year_1980_to_2009() -> None:
    t = dblp_aaai_table.TABLE
    assert set(t.years) | t.not_held == set(range(1980, 2010)) and not set(t.years) & t.not_held
    assert sorted(t.years) == [1980, 1982, 1983, 1984, 1986, 1987, 1988, *range(1990, 2001), 2002, *range(2004, 2009)]
    assert all(len(t.years[y].proceedings) == 2 for y in (1986, 1991, 1994, 1996))
    assert sum(y.papers for y in t.years.values()) == CENSUS_MAIN  # the census total, written in as a literal
```

- [ ] **Step 6: Research note.** Add "§AAAI 1980–2008 (dblp)": the per-year counts table, the split years' keys, the workshop and excluded keys, the not-paper rows with reasons, the IAAI cross-check, the homonym and DOI counts, and the candidates left for owner review. Name the release DOI and the ICML extract hash (unchanged).

- [ ] **Step 7: Run and commit**

Run: `uv run pytest backend/tests/unit/ingest -q -n auto` and `make lint`. Expected: PASS.

```bash
git add -A backend scripts docs
git commit -m "data: dblp AAAI 1980-2008 table from the pinned release (main keys, split years, not-paper rows); research note"
```

---

### Task 9: Census B (live): Crossref ACM table, FAccT 2020 not-paper list, PMLR v81 row, FAccT site pages

The controller runs this, with network, in a scratch data dir: `C=/private/tmp/op-b-census`. `CROSSREF_MAILTO` must be set in `.env`.

**Files:**
- Create: `scripts/acm_census.py` (read-only helper, driven through `crawl.crossref_fetcher`)
- Modify: `backend/src/openproceedings/ingest/acm_proceedings.toml` (14 `[[proceedings]]` rows; the `[[not_paper]]` rows)
- Modify: `backend/src/openproceedings/ingest/pmlr_volumes.toml` (the v81 row)
- Modify: `backend/tests/fixtures/http/scrub.py` (`scrub_crossref`: titles, subtitles and authors become synthetic, while DOIs, types, pages, cursors and totals stay; long pages are trimmed to the toc's items plus 3 foreign ones, with `_recorded.trimmed`; `scrub_csv`: free-text columns become synthetic, while ID, TYPE and URL/DOI stay)
- Create fixtures:
  - `backend/tests/fixtures/http/crossref/facct-2019-proceedings.json`, `facct-2019-works-<n>.json` (every page of the 2019 chain, trimmed);
  - `backend/tests/fixtures/http/pmlr/v81/volume-index.json`;
  - `backend/tests/fixtures/http/facct_site/{2022-acceptedpapers,2025-final,2026-final}.json` (scrubbed, trimmed to about 20 entries each, the 2022 page keeping its full HTML structure);
  - `backend/tests/fixtures/http/facct_site/robots.json`.
- Create: `backend/tests/unit/ingest/crossref/test_crossref_recorded.py`; Modify: `backend/tests/unit/ingest/test_pmlr.py` (pin v81 to its recorded index)
- Modify: the research note (§FAccT, §AIES, §FAccT site)

- [ ] **Step 1: Write `scripts/acm_census.py`.** For each of the 14 proceedings DOIs (from the research note; a literal list in the script), through `crawl.crossref_fetcher(C/cache, offline=False)`:
  1. Read the proceedings record: title, ISBNs and `published` date.
  2. Walk a wide window (published ± 120 days) with `crossref._walk` on a throwaway `Proceedings`, and collect every DOI extending the toc, with its `published` date-parts, type, `page` and title.
  3. Read `works?filter=prefix:10.1145,isbn:<isbn>&rows=0` and take its `total-results` (the independent count).
  4. Propose `window_from = min(published) − 7 days` and `window_until = max(published) + 7 days`.
  5. Print not-paper candidates: a `page` spanning at most one page (`"690"`, `"690-690"`), a title beginning `Tutorial`, `CRAFT`, `Keynote` or `Panel`, or a type other than `proceedings-article`.
  6. Print draft TOML.

- [ ] **Step 2: Run it**:

```bash
OP_DATA_DIR=/private/tmp/op-b-census uv run python scripts/acm_census.py --cache /private/tmp/op-b-census/cache | tee "$TMPDIR/acm-census.txt"
```

  Expected: toc counts matching the research note (FAccT 41, 95, 82, 181, 153, 167, 206, 314; AIES 78, 91, 76, 114, 115, 101). Any difference, from the note or from the ISBN route, is explained in the research note before a row is written.

- [ ] **Step 3: Write the rows.**
  - Fourteen `[[proceedings]]` rows: `dois` = the toc count, with the proposed window and dblp-style `verified`/`source`.
  - FAccT 2020's tutorial and CRAFT entries as `[[not_paper]]` rows by DOI (about 27). Kind `tutorial` or `craft session`, and a reason naming the page span and title form.
  - Any other year's keynotes or front matter, likewise. The controller confirms each.
  - AIES entries of two pages or fewer are listed in the note for owner review and stay `main`.

  Then run:

```bash
OP_DATA_DIR=/private/tmp/op-b-census uv run op ingest crossref
```

  Expected: 14 listings, each `count_ok: true`, `no_authors` 0 or explained.

- [ ] **Step 4: PMLR v81.**
  1. Read the live index once through `crawl.fetcher(C/cache, "pmlr", pmlr.HOSTS, offline=False)` and print `pmlr.heading(...)` and `pmlr.parse_volume_index(...)` (key, title, authors).
  2. Identify the preface and the two keynotes.
  3. Write the row: `number = 81`, `venue = "FAccT"`, `year = 2018`, `track = "main"`, `role = "primary"`, `papers = 20`, `not_papers = [<3 keys>]`, plus `heading`, `index_title`, `verified`, `source`.
  4. Run `OP_DATA_DIR=/private/tmp/op-b-census uv run op ingest pmlr --venue FAccT --year 2018`. Expected: v81 `count_ok`, 17 records, `skipped: {"not_paper": 3}`.
  5. Record the index fixture. In `test_pmlr.py`, add `("pmlr/v81/volume-index.json", 81)` to `test_the_table_agrees_with_the_recorded_volume_headings`, plus a test that the recorded index's keys include every `not_papers` key.

- [ ] **Step 5: FAccT site.**
  1. Fetch `https://facctconference.org/robots.txt` and the three pages through a fetcher on `facctconference.org` with `expect="text"`.
  2. Count the entries: the 2025 and 2026 CSVs with `csv.DictReader` (expected 217 and 325; check the column headers), and the 2022 page by inspecting its structure. Write down the element that holds each paper's title and abstract; Task 10's `facct2022_html` parser is written against it.
  3. Count the 2025 rows with a `10.1145/3715275.` DOI in `URL`.
  4. Record the scrubbed, trimmed fixtures.

- [ ] **Step 6: Recorded tests.**

```python
# backend/tests/unit/ingest/crossref/test_crossref_recorded.py
"""Recorded Crossref pages (2026-10-10, scrubbed: real DOIs, cursors and counts; synthetic titles and authors)
pinned to the shipped table: FAccT 2019's chain mines to its table count."""

from pathlib import Path

from openproceedings.ingest import acm_table
from openproceedings.ingest.sources import crossref
from openproceedings.ingest.sources.http import Fetcher, PageCache

from tests.unit.ingest.proceedings_helpers import fixture, seed

CR = Path(__file__).parents[3] / "fixtures" / "http" / "crossref"


def test_facct_2019_mines_to_its_table_count(tmp_path: Path) -> None:
    for p in CR.glob("facct-2019-*.json"):
        f = fixture(f"crossref/{p.name}")
        seed(tmp_path, "crossref", f["request"]["url"], f["response"]["text"], keep_query=True)
    offline = Fetcher(PageCache(tmp_path / "crossref"), None, hosts=crossref.HOSTS, expect="json", keep_query=True)
    result = crossref.mine_proceedings("FAccT", 2019, offline)
    assert len(result.records) == acm_table.TABLE.expected("FAccT", 2019)
    assert all(r.title.startswith("Synthetic title") for r in result.records)
```

  Also add `test_the_shipped_table_has_every_acm_proceedings` in `test_acm_table.py`. It asserts the 14 (venue, year) keys and the 14 DOIs above, `sum(p.dois for p in TABLE.proceedings.values()) == 1341 + 575` (or the census's corrected totals, written as literals), and that FAccT 2020 has `CENSUS_2020_NOT_PAPERS` rows.

- [ ] **Step 7: Research note.** Add or extend:
  - **§FAccT:** the windows and how they were chosen, the ISBN cross-check results, the FAccT 2020 not-paper summary, the v81 facts.
  - **§AIES:** the counts and the two-pages-or-fewer list for owner review.
  - **§FAccT site:** robots.txt, the three pages, their entry counts, the 2025 DOI coverage, and the 2026 rows expected to stay unmatched (non-archival).
  - **§Official counts:** none gated, and why.

- [ ] **Step 8: Run and commit**

Run: `uv run pytest backend/tests -q -n auto` and `make lint`. Expected: PASS.

```bash
git add -A backend scripts docs
git commit -m "data: acm_proceedings.toml and the PMLR v81 row from the live census (FAccT 2018-2026, AIES 2018-2023, FAccT 2020 tutorial and CRAFT rows); recorded fixtures; research note"
```

---

### Task 10: Official FAccT abstracts (`facct_site`)

**Files:**
- Create: `backend/src/openproceedings/ingest/facct_site.toml` (three rows, from Task 9's counts), `backend/src/openproceedings/ingest/sources/facct_site.py`
- Modify: `backend/src/openproceedings/ingest/sources/crossref.py` (`mine_proceedings(..., site=None)`, the site fields on `CrossrefReport`, the abstract claim in `_record`)
- Modify: `backend/src/openproceedings/ingest/sources/crawl.py` (`facct_site_fetcher`; `ingest_crossref` and the `CROSSREF` replay read the year's site pages for FAccT)
- Create: `backend/tests/unit/ingest/crossref/test_facct_site.py`, `test_facct_site_recorded.py`

**Interfaces:**
- Consumes: Tasks 7 and 9.
- Produces:
  - `facct_site.SOURCE = "facct_site"`, `CACHE_DIR = "facct_site"`, `HOST = "facctconference.org"`, `HOSTS`, `MIN_INTERVAL = 1.0`;
  - `facct_site.SitePage(year, url, parser, join, rows, verified, note)`, `facct_site.Entry(key, title, abstract, doi)`;
  - `facct_site.SiteAbstract(key, title, doi, abstract, spaced, pdf_codes, url, fetched_at, evidence)`, `facct_site.SiteYear(page, join, entries, fetched, dropped)`;
  - `facct_site.PARSERS`, `facct_site.load(text)`, `facct_site.TABLE`;
  - `facct_site.read_year(year, fetcher, *, refresh=False, table=None) -> SiteYear | None`;
  - `facct_site.match(papers: Sequence[tuple[str, str]], site: SiteYear) -> Matched(by_doi: dict[str, SiteAbstract], unmatched: int, ambiguous: int)`;
  - `crossref.mine_proceedings(..., site: SiteYear | None = None)`;
  - `CrossrefReport` gains `sites`, `site_entries`, `abstract_attached`, `site_unmatched`, `site_ambiguous`, `site_dropped`, listed in the manifest only when `sites` is non-empty.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/unit/ingest/crossref/test_facct_site.py
from pathlib import Path

import pytest
from openproceedings.ingest import acm_table
from openproceedings.ingest.dedup import attribution
from openproceedings.ingest.sources import crossref, facct_site
from openproceedings.ingest.sources.common import CrawlError

from tests.unit.ingest.crossref import api
from tests.unit.ingest.crossref.test_crossref_mine import D1, D2, NP, TABLE, _offline, _whole
from tests.unit.ingest.proceedings_helpers import fetcher, seed

URL26 = "https://facctconference.org/static/docs/facct2026-final.csv"
URL25 = "https://facctconference.org/static/docs/facct2025-final.csv"
SITE_TABLE = f"""
[[page]]
year = 2023
url = "{URL26}"
parser = "facct2026_csv"
join = "title"
rows = 3
verified = 2026-10-10
note = "test"
"""


def csv26(*rows: tuple[str, str, str]) -> str:
    lines = ["Paper ID,Title,Authors,Abstract"] + [f'{i},"{t}","Synthetic Author","{a}"' for i, t, a in rows]
    return "\ufeff" + "\r\n".join(lines) + "\r\n"


def site(tmp_path: Path, text: str, table: str = SITE_TABLE) -> facct_site.SiteYear:
    seed(tmp_path, "facct_site", URL26, text)
    f, _ = fetcher(tmp_path / "facct_site", None, facct_site.HOSTS, expect="text")
    got = facct_site.read_year(2023, f, table=facct_site.load(table))
    assert got is not None
    return got


@pytest.fixture(autouse=True)
def _acm(monkeypatch):
    monkeypatch.setattr(acm_table, "TABLE", TABLE)


def test_a_title_join_attaches_the_official_abstract_credited_to_the_doi_link(tmp_path: Path) -> None:
    _whole(tmp_path, api.work(D1, title="Fair Ranking, Revisited"), api.work(D2, title="Other"), api.work(NP), total=3)
    s = site(tmp_path, csv26(("1", "fair ranking revisited", "Official abstract one."),
                             ("2", "A non-archival talk", "Abstract two."), ("3", "", "No title here.")))
    result = crossref.mine_proceedings("FAccT", 2023, _offline(tmp_path), table=TABLE, site=s)
    r = next(x for x in result.records if x.urls.doi == D1)
    assert r.abstract == "Official abstract one."
    (claim,) = r.claims("abstract")
    assert (claim.source, claim.url) == ("facct_site", URL26) and "title key" in (claim.evidence or "")
    att = attribution(r.abstract, r.provenance, forum=None, proceedings=r.urls.proceedings, native=r.native)
    assert att is not None and att.url == f"https://doi.org/{D1}"  # never the CSV
    report = result.reports[0]
    assert (report.site_entries, report.abstract_attached, report.site_unmatched, report.site_ambiguous,
            report.site_dropped) == (2, 1, 1, 0, 1)  # fmt: skip


def test_two_rows_sharing_a_title_key_attach_nothing(tmp_path: Path) -> None:
    _whole(tmp_path, api.work(D1, title="Fair Ranking"), api.work(D2, title="Other"), api.work(NP), total=3)
    s = site(tmp_path, csv26(("1", "Fair Ranking", "A."), ("2", "FAIR ranking!", "B."), ("3", "Other", "C.")))
    result = crossref.mine_proceedings("FAccT", 2023, _offline(tmp_path), table=TABLE, site=s)
    assert next(x for x in result.records if x.urls.doi == D1).abstract is None
    assert next(x for x in result.records if x.urls.doi == D2).abstract == "C."
    assert (result.reports[0].site_ambiguous, result.reports[0].abstract_attached) == (2, 1)


def test_two_records_sharing_a_title_key_attach_nothing(tmp_path: Path) -> None:
    _whole(tmp_path, api.work(D1, title="Same"), api.work(D2, title="same."), api.work(NP), total=3)
    s = site(tmp_path, csv26(("1", "Same", "A."), ("2", "x", "B."), ("3", "y", "C.")))
    result = crossref.mine_proceedings("FAccT", 2023, _offline(tmp_path), table=TABLE, site=s)
    assert all(r.abstract is None for r in result.records) and result.reports[0].site_ambiguous == 1


def test_a_doi_join_never_falls_back_to_the_title() -> None:
    entries = [facct_site.SiteAbstract("1", "Fair", D1, "A.", 0, 0, URL25, api_t(), "e"),
               facct_site.SiteAbstract("2", "Other", None, "B.", 0, 0, URL25, api_t(), "e"),
               facct_site.SiteAbstract("3", "x", D2, "C.", 0, 0, URL25, api_t(), "e"),
               facct_site.SiteAbstract("4", "y", D2, "D.", 0, 0, URL25, api_t(), "e")]
    s = facct_site.SiteYear(URL25, "doi", entries, [api_t()], 0)
    got = facct_site.match([(D1, "Fair"), (D2, "Other"), ("10.1145/3715275.9", "Other")], s)
    assert set(got.by_doi) == {D1} and (got.unmatched, got.ambiguous) == (1, 2)  # no DOI → unmatched, never by title


def api_t():
    from tests.unit.ingest.crossref.test_crossref_parse import T
    return T


@pytest.mark.parametrize(
    ("text", "reason"),
    [("a,b\n1,2\n", "site_format"), (csv26(("1", "x", "y")), "site_count"),
     (csv26(("1", "x", "y"), ("1", "z", "w"), ("3", "q", "r")), "site_duplicate_key")],
)  # fmt: skip
def test_a_page_that_is_not_what_the_table_says_stops(tmp_path: Path, text: str, reason: str) -> None:
    with pytest.raises(CrawlError) as e:
        site(tmp_path, text)
    assert e.value.reason == reason


def test_a_page_that_is_gone_stops(tmp_path: Path) -> None:
    seed(tmp_path, "facct_site", URL26, "", status=404)
    f, _ = fetcher(tmp_path / "facct_site", None, facct_site.HOSTS, expect="text")
    with pytest.raises(CrawlError) as e:
        facct_site.read_year(2023, f, table=facct_site.load(SITE_TABLE))
    assert e.value.reason == "site_missing"


@pytest.mark.parametrize(
    ("edit", "message"),
    [(lambda s: s.replace('join = "title"', 'join = "fuzzy"'), "join"),
     (lambda s: s.replace('parser = "facct2026_csv"', 'parser = "nope"'), "parser"),
     (lambda s: s.replace("facctconference.org", "example.org"), "facctconference.org"),
     (lambda s: s.replace("rows = 3", "rows = 0"), "positive"),
     (lambda s: s + s, "one page per year")],
)  # fmt: skip
def test_bad_rows_are_refused(edit, message) -> None:
    with pytest.raises(ValueError, match=message):
        facct_site.load(edit(SITE_TABLE))


def test_the_2025_csv_reads_its_doi_from_the_url_column() -> None:
    text = ("TYPE,ID,ABSTRACT,AUTHOR,TITLE,URL\r\nPaper,7,An abstract.,Synthetic Author,A title,"
            "https://dl.acm.org/doi/10.1145/3715275.3732001\r\nTalk,8,Other.,Synthetic Author,B title,\r\n")  # fmt: skip
    (a, b) = facct_site.facct2025_csv(text)
    assert (a.key, a.doi, b.doi) == ("7", "10.1145/3715275.3732001", None)
```

`test_facct_site_recorded.py`: each recorded page parses with its table row's parser to the fixture's trimmed entry count (the fixture's `_recorded.trimmed` gives the trimmed count). The 2025 fixture's DOIs all extend `10.1145/3715275.`. The shipped `facct_site.TABLE` has exactly years 2022, 2025 and 2026, with `rows` equal to Task 9's live counts (217 and 325 for the CSVs).

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest backend/tests/unit/ingest/crossref/test_facct_site.py -q`. Expected: FAIL (`ModuleNotFoundError: facct_site`).

- [ ] **Step 3: Implement `sources/facct_site.py`**

The docstring covers:
- the three official pages and that robots.txt allows everything;
- each page in `facct_site.toml` with its parser, its join rule and its verified row count;
- the join: a 2025 row by DOI only; a 2022 or 2026 row by exact title key (`dedup.title_key`), attached only when one entry and one record share it;
- what is counted, never forced: unmatched, ambiguous, and rows with no title or no usable abstract (`site_dropped`);
- the abstract claim: url = the page as fetched, evidence = row id and join rule. Attribution credits the DOI link (`dedup.attribution`).

```python
SOURCE: Source = "facct_site"
CACHE_DIR = "facct_site"
HOST = "facctconference.org"
HOSTS = frozenset({HOST})
MIN_INTERVAL = 1.0
_DOI = re.compile(r"10\.1145/[0-9]+\.[0-9]+", re.IGNORECASE)
_COLUMNS = {"year", "url", "parser", "join", "rows", "verified", "note"}


def _csv(text: str, columns: tuple[str, ...], *, key: str, title: str, abstract: str,
         doi_from: str | None = None) -> list[Entry]:  # fmt: skip
    reader = csv.DictReader(io.StringIO(text.removeprefix("\ufeff"), newline=""))
    if tuple(reader.fieldnames or ()) != columns:
        raise CrawlError(f"a FAccT CSV's columns are {reader.fieldnames}, not {list(columns)}: check facct_site.toml",
                         reason="site_format")  # fmt: skip
    out = []
    for row in reader:
        if None in row or any(v is None for v in row.values()):
            raise CrawlError("a FAccT CSV row has more or fewer fields than its header", reason="site_format")
        doi = m.group(0).lower() if doi_from and (m := _DOI.search(row[doi_from])) else None
        out.append(Entry(row[key].strip(), row[title].strip() or None, row[abstract].strip() or None, doi))
    return out


def facct2025_csv(text: str) -> list[Entry]:
    return _csv(text, ("TYPE", "ID", "ABSTRACT", "AUTHOR", "TITLE", "URL"), key="ID", title="TITLE",
                abstract="ABSTRACT", doi_from="URL")  # fmt: skip


def facct2026_csv(text: str) -> list[Entry]:
    return _csv(text, ("Paper ID", "Title", "Authors", "Abstract"), key="Paper ID", title="Title", abstract="Abstract")
```

`facct2022_html(text) -> list[Entry]` is written against Task 9's recorded page structure, with `sources/html.py` (`parse`, `node_text`). The key is the entry's position, or an id if the page gives one. The page's paper count is the table's `rows`. Add one test of it on a synthetic snippet with the page's real structure.

`PARSERS = {"facct2022_html": facct2022_html, "facct2025_csv": facct2025_csv, "facct2026_csv": facct2026_csv}`.

`load` validates each row:
- known columns;
- `venue_name("FAccT", year)` holds;
- the url is https on `HOST` ("facctconference.org");
- the parser is in `PARSERS` ("parser");
- join is `"doi"` or `"title"` ("join");
- rows is a positive int ("positive");
- a date and a note;
- one page per year ("one page per year").

`read_year`:
- Reads the year's row (None when there is none) with `fetcher.get(url, refresh=refresh)`. A page that is not OK raises `site_missing`.
- Runs the parser. A count other than `rows` raises `site_count`; a repeated key raises `site_duplicate_key`.
- Per entry, `title = title_text(e.title)[0] if e.title else ""` and `cleaned = clean_abstract(e.abstract)`. No title or no abstract adds to `dropped`. Otherwise it builds a `SiteAbstract` with `evidence = f"{p.url} row {e.key}"`.
- Logs `facct_site_year_read` (year, entries, dropped).

`match`:
- For `doi`: group the entries by DOI. A `None` DOI, or one no paper has, adds to `unmatched`. A group of two or more adds to `ambiguous`. Otherwise attach.
- For `title`: the `dblp._match` rule over `title_key`, keyed by DOI.

- [ ] **Step 4: Wire it in**

`crossref.mine_proceedings(..., site=None)`:
- After the not-paper and title checks, collect `kept = [(doi, w, page)]` and run `matched = facct_site.match([(doi, w.title) for …], site) if site else None`.
- Fill the report's site fields: `sites=[site.page]`, `site_entries=len(site.entries)`, `site_dropped=site.dropped`, unmatched and ambiguous from `matched`. Add `site.fetched` to `report.fetched`.
- Pass `found = matched.by_doi.get(doi)` to `_record`. When `found` is set, `_record` adds:

```python
        claims.append(Claim(field="abstract", value=found.abstract, source=facct_site.SOURCE, url=found.url,
                            fetched_at=found.fetched_at, evidence=pdf_codes_evidence(controls_evidence(
                                f"{found.evidence}; joined to {w.doi} by {'DOI' if site.join == 'doi' else 'its title key, the record’s alone'}",
                                found.spaced), found.pdf_codes)))  # fmt: skip
```

- `report.count(record, None if record.abstract else "no_abstract", found.spaced if found else 0, found.pdf_codes if found else 0)`; then `abstract_attached = sum(r.abstract is not None for r in records)`.

`crawl.py`:

```python
def facct_site_fetcher(cache: Path, *, offline: bool, transport: Transport | None = None,
                       min_interval: float = DEFAULT_INTERVAL) -> Fetcher:  # fmt: skip
    live = None if offline else (transport or urllib_transport)
    return Fetcher(PageCache(cache / facct_site.CACHE_DIR), live, hosts=facct_site.HOSTS,
                   min_interval=max(min_interval, facct_site.MIN_INTERVAL), accept="text/csv, text/html",
                   expect="text")  # fmt: skip
```

In `ingest_crossref`, the crawl lambda becomes `crossref.mine_proceedings(v, y, f, refresh=refresh, table=table, site=facct_site.read_year(y, sf, refresh=refresh) if v == "FAccT" else None)`. The `CROSSREF` replay does the same with offline fetchers. Add a test in `test_crossref_crawl.py`: with the site page seeded, `ingest_crossref` offline and the replay give the same abstract.

- [ ] **Step 5: Write the shipped table** (`facct_site.toml`). The header documents the columns. The three rows:
  - 2022: `url = "https://facctconference.org/2022/acceptedpapers.html"`, `parser = "facct2022_html"`, `join = "title"`, `rows` = Task 9's count;
  - 2025: `.../static/docs/facct2025-final.csv`, `facct2025_csv`, `join = "doi"`, `rows = 217`;
  - 2026: `.../static/docs/facct2026-final.csv`, `facct2026_csv`, `join = "title"`, `rows = 325`.

  Each has `verified` and a `note`.

- [ ] **Step 6: Run the full backend suite and commit**

Run: `uv run pytest backend/tests -q -n auto` and `make lint`. Expected: PASS.

```bash
git add -A backend
git commit -m "feat: official FAccT abstracts (2022, 2025, 2026) joined by DOI or one-to-one title key; unmatched and ambiguous counted"
```

---

### Task 11: Docs as built

**Files:**
- Modify `docs/specs/00-overview.md`: §Scope, so the venue spans read as built (AAAI from 1980, AIES from 2018, FAccT from 2018, IASEAI 2026).
- Modify `docs/specs/01-ingestion.md`:
  - §Record schema: the `id` row (`doi-<toc>.<n>`, AAAI `dblp-`, FAccT `pmlr-v81-`), the `venue` row (schema 7 and its sources);
  - §Track taxonomy: the `main` row (dblp AAAI main keys; every ACM paper but `not_paper`; v81) and the `workshop` row (dblp AAAI workshop keys);
  - §Sources: the dblp row widened to AAAI (the separate extract and why, `dblp_aaai.toml`, not-held years, not-paper rows counted, the count stop in every replay, the venue-scoped takedown link); the PMLR row (v81, `not_papers`, the non-ICML count stop, `PMLR_NATIVE_VOLUMES` versus the ICML-only maps); a new **Crossref** row (the route, sequential requests with the `CROSSREF_MAILTO` User-Agent, the cursor rule, the window and the ISBN cross-check, every stop reason, the claim url, no abstracts); a new **FAccT site** row (pages, parsers, join rules, counts, attribution);
  - §Crawl window; §CLI (`op ingest dblp --venue`, `op ingest pmlr --venue`, `op ingest crossref`); the manifest `sources` keys (`crossref`; the new report fields).
- Modify `docs/specs/04-backend-api.md` (`ORIGIN_NAMES` and `ORIGIN_DOC` gain Crossref and FAccT conference site), `docs/specs/05-frontend.md` and `docs/design/2026-09-27-copy-deck.md` (CV-7 venue spans; RH-12 origin names), `docs/specs/07-evaluation.md` (the new coverage cells and why none is gated), `docs/specs/08-ops-and-tooling.md` (the commands; crawl order `…, ojs, crossref`; the design's `facct-site` target folded into `crossref`).
- Modify `README.md` and `CLAUDE.md`:
  - CLAUDE.md's first line: "AAAI (from 1980), AIES (from 2018), FAccT (from 2018) and IASEAI (2026)";
  - the `ingest/` layout line gains `dblp_aaai_table.py` + `dblp_aaai.toml`, `acm_table.py` + `acm_proceedings.toml`, `facct_site.toml`, and `sources/dblp_aaai.py`, `crossref.py`, `facct_site.py`;
  - `op ingest … | crossref`.
- Modify `frontend/src/app/page.tsx`, `frontend/src/app/layout.tsx` and `frontend/src/components/coverage/coverage-report.tsx`, if they print venue spans.
- Modify `docs/plans/2026-10-09-new-venues-design.md`: the status line says milestone B is built; its "Where each venue-year comes from" table gets the as-built counts; the planner decisions the controller accepted go into a short "Milestone B as built" note.
- Edit decision-049's body (consequences: schema 7, the B sources). Decision bodies may be edited by hand per `enforce-backlog-cli.sh`.
- Modify skills: `.claude/skills/record-schema/SKILL.md` (native forms, schema 7), `pmlr-proceedings` (FAccT v81, `not_papers`), `track-taxonomy` (main and workshop rows), `dedup-rules` (attribution for crossref and facct_site; the venue-scoped dblp takedown link).
- Modify `docs/README.md` (research row), `cspell.json` (`Crossref`, `FAccT`, `toc`, `CRAFT`, `mailto`, if flagged).
- Backlog: run `backlog instructions overview`, then append to TASK-202's notes: "Milestone B adds `op ingest crossref` (with the FAccT site pages) and `op ingest dblp --venue AAAI` / `op ingest pmlr --venue FAccT`; a full run orders …, ojs, crossref; CROSSREF_MAILTO must be in the scheduled environment."

- [ ] **Step 1:** Edit each document above as built in Tasks 1–10. Write no future tense for what this milestone built; name milestone C's pieces as planned, with a link to the design.
- [ ] **Step 2:** Run `make lint` and `make tooling` (skills changed). Expected: PASS.
- [ ] **Step 3:** Commit. Add new files explicitly.

```bash
git add -A docs README.md CLAUDE.md .claude frontend cspell.json
git commit -m "docs: specs, decision-049, README, skills and copy for AAAI 1980-2008, FAccT and AIES 2018-2023 (milestone B as built)"
```

---

### Task 12: Real-data verification, then the closing workflow

The controller runs this in the foreground (agents stall on background runs). `export OP_DATA_DIR=/Users/jeevanparmar/school/Research/Ferguson/openproceedings/data`. That data dir is outside the worktree. `CROSSREF_MAILTO` must be set in `.env`.

- [ ] **Step 1: ICML's extract hash before**:

```bash
shasum -a 256 "$OP_DATA_DIR/cache/dblp/extract/20e45961bec5610dc07b8e932ccd27a2387534cfa12c92a24289fe873aebe969.json"
```

- [ ] **Step 2: AAAI from dblp**:

```bash
uv run op ingest dblp --venue AAAI --year 1980-2008
```

  Expected: 24 listings, each `count_ok: true`; `not_held: [1981, 1985, 1989, 2001, 2003]`. Step 1's hash is unchanged. Then run `uv run op ingest dblp --year 1988-2012 --offline`; its listings must equal those of the last ICML run.

- [ ] **Step 3: FAccT 2018**:

```bash
uv run op ingest pmlr --venue FAccT --year 2018
```

  Expected: v81 `count_ok`, 17 records, `skipped: {"not_paper": 3}`.

- [ ] **Step 4: Crossref and the FAccT site**:

```bash
uv run op ingest crossref
```

  Expected: 14 listings, each `count_ok: true`. FAccT 2022, 2025 and 2026 report `abstract_attached`, `site_unmatched` and `site_ambiguous`. The 2025 attached count is close to its DOI-bearing rows; 2026's unmatched is at least its non-archival rows. Write all three into the PR body.

- [ ] **Step 5: Snapshot and diff**:

```bash
uv run op snapshot build
uv run op snapshot diff "$OP_DATA_DIR/snapshots/<latest before B>" "$OP_DATA_DIR/snapshots/<new>"
```

  Expected: additions only. About 3.7k `op:aaai:<1980-2008>:dblp-*`, the FAccT `doi-*` and `pmlr-v81-*` ids (FAccT total = sum of `dois` − not-paper rows + 17) and the AIES `doi-*` ids. 0 removed, 0 changed, 0 rekeyed. Cite both snapshot hashes in the PR.

- [ ] **Step 6: Index and parity**:

```bash
uv run op index build --snapshot <new snapshot hash>
uv run op index parity --index <new index_version>
```

  Expected: parity holds over the full corpus.

- [ ] **Step 7: Coverage**:

```bash
uv run op eval coverage --index <new index_version> --check
```

  Expected:
  - every new venue-year appears at its table count;
  - unknown-track cells are 0 for the new venues;
  - the methods-section scope prints separate ICML and AAAI dblp sentences;
  - the gate passes.

  Commit the report under `docs/results/` (`docs: coverage report on index <version> (milestone B)`).

- [ ] **Step 8: Closing workflow** (CLAUDE.md, in order):
  1. `make test` (full), `make lint` and `make tooling`.
  2. Bring the backlog current. File follow-up tasks last:
     - the AIES two-pages-or-fewer entries and the dblp not-paper candidates for owner review;
     - any `no_authors` works;
     - AIES 2026 as an OJS table row once published;
     - IASEAI 2027 via OpenReview after 2026-11-20 (if not already filed).
  3. `/record-learnings`.
  4. `/review-gate`, with every Must and Should fixed.
  5. Push; `/open-pr` into `dev`; `gh pr merge <n> --auto`.

### Critical Files for Implementation
- /Users/jeevanparmar/school/Research/Ferguson/openproceedings-wt-new-venues/backend/src/openproceedings/ingest/record.py
- /Users/jeevanparmar/school/Research/Ferguson/openproceedings-wt-new-venues/backend/src/openproceedings/ingest/sources/dblp.py
- /Users/jeevanparmar/school/Research/Ferguson/openproceedings-wt-new-venues/backend/src/openproceedings/ingest/sources/crawl.py
- /Users/jeevanparmar/school/Research/Ferguson/openproceedings-wt-new-venues/backend/src/openproceedings/ingest/urls.py
- /Users/jeevanparmar/school/Research/Ferguson/openproceedings-wt-new-venues/backend/src/openproceedings/ingest/dedup.py
