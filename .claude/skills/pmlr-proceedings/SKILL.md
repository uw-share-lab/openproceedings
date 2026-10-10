---
name: pmlr-proceedings
description: The PMLR (proceedings.mlr.press) source for ICML — the volume table (ingest/pmlr_volumes.toml, loaded and checked by ingest/volumes.py, which derives `ICML_PMLR_VOLUMES`), the known ICML volumes 2013–2025, competition and workshop volumes, page structure and parsing gotchas, the miner (ingest/sources/pmlr.py, `op ingest pmlr`), and why an unfamiliar volume is never coerced into ICML. Use when writing or reviewing the PMLR miner, editing the volume table, or adding an ICML year.
---

# PMLR proceedings (spec 01 §Sources)

PMLR is the **primary** source for ICML 2013–2022 (not on OpenReview as full venues; PMLR starts at v28,
2013, and ICML 1988–2012 comes from the pinned dblp release instead, decision-047, `ingest/sources/dblp.py`) and a confirming source for ICML 2023+ (OpenReview v2 is primary there; a paper on
OpenReview but not in PMLR, or the reverse, is a `conflicts.csv` row).

## The volume table is data
As built (task-053): `backend/src/openproceedings/ingest/pmlr_volumes.toml`, one `[[volume]]` row per
volume with `number`, `venue`, `year`, `track`, `role` (`primary` | `confirm` | `out_of_scope`), `papers`
(the verified `<div class="paper">` count), `heading` (what the page's `Volume N: ` heading starts with),
`index_title`, `verified` (a TOML date) and `source`. `ingest/volumes.py` loads it at import and refuses a
malformed table (unknown column or value, duplicate volume, two ingested volumes for one venue-year, an
ingested competition/workshop or non-ICML row, an ingested row without year, count or heading).
`ICML_PMLR_VOLUMES` (volume → year, track) is derived from the ingested ICML rows; the RIS importer,
`urls.native` and the miner all read this one table, and no other module holds a volume number.
`test_ris.py` pins `ICML_PMLR_VOLUMES`; `test_pmlr.py` checks every row against the recorded PMLR index and
volume headings. **Adding an ICML row changes the RIS import** (a `pmlr_url` in that volume becomes an ICML
record instead of a `no_id`/`out_of_scope` skip), so a new row shows in the next `op snapshot diff`.

Every row was verified live on 2026-09-27 against the volume page's heading
(`<h2>Volume N: International Conference on Machine Learning, <dates>, <place></h2>`) and the PMLR index
title; the paper count is the number of `<div class="paper">` entries (evidence:
`docs/research/2026-09-27-openreview-and-proceedings-facts.md`; fixtures `backend/tests/fixtures/http/pmlr/`).

| Volume | Venue | Year | Track | Role | Papers |
|---|---|---|---|---|---|
| v28 | ICML | 2013 | `main` | primary | 283 |
| v32 | ICML | 2014 | `main` | primary | 310 |
| v37 | ICML | 2015 | `main` | primary | 270 |
| v48 | ICML | 2016 | `main` | primary | 322 |
| v70 | ICML | 2017 | `main` | primary | 434 |
| v80 | ICML | 2018 | `main` | primary | 621 |
| v97 | ICML | 2019 | `main` | primary | 773 |
| v119 | ICML | 2020 | `main` | primary | 1,084 |
| v139 | ICML | 2021 | `main` | primary | 1,183 |
| v162 | ICML | 2022 | `main` | primary | 1,233 |
| v202 | ICML | 2023 | `main` | confirm | 1,828 (= OpenReview accepted) |
| v235 | ICML | 2024 | `unknown` | confirm | 2,610 (= OpenReview, position papers included and unmarked) |
| v267 | ICML | 2025 | `unknown` | confirm | 3,330 (= OpenReview 3,257 main + 73 position) |
| – | ICML | 2026 | – | – | not on PMLR on 2026-09-27: add the row when its index page appears |
| v123 | NeurIPS | 2019 | `competition` | out_of_scope | 23 (Competition and Demonstration Track) |
| v133 | NeurIPS | 2020 | `competition` | out_of_scope | 20 |
| v176 | NeurIPS | 2021 | `competition` | out_of_scope | 36 (sections "Competitions", "Demonstrations") |
| v220 | NeurIPS | 2022 | `competition` | out_of_scope | 20 |

The NeurIPS competition volumes are classified but not ingested: spec 01 lists PMLR for ICML only, and a
`pmlr-` native id is ICML-only in the record schema, so ingesting them needs a spec and schema change (FAccT 2018's PMLR v81 is planned for milestone B of the new-venues design, decision-049, and widens `PROCEEDINGS_NATIVE["pmlr"]` then; it is not built).

ICML workshop volumes exist and are **out of scope** (never `main`, never ingested unless spec 01 adds
workshops from PMLR): v27 (2011), v184 (ICML 2022 Healthcare AI), v251 (GRaM at ICML 2024), v292
(TerraBytes at ICML 2025). NeurIPS workshop volumes likewise (v116, v136, v137, v163, v181, v187, v210,
v226, v239, v262; the table gives them no year, since the research run didn't record one). All are
`out_of_scope` rows in the table. v28 and v32 split their papers into "Cycle 1/2/3 Papers" sections, which are not
tracks.

**Position papers:** no ICML volume marks them (v235 and v267 have no section headings), so the track
comes from OpenReview (`ICML.cc/2025/Position_Paper_Track`), and PMLR only confirms acceptance. ICML 2024's
position papers aren't marked on OpenReview either (they carry `ICML.cc/2024/Conference`).
Paper entries in the recorded v202, v235 and v267 indexes link the OpenReview forum
(`openreview.net/forum?id=…`): dedup's forum link joins PMLR and OpenReview on that id for 2023+, before
and whatever the title (TASK-105, `dedup-rules`). The recorded v28 paper page has no forum link and pins
the older per-paper shape. Exactly one distinct forum id is required: repeated copies of the same id
collapse, while an entry naming two different forum ids is skipped before title-based dedup can merge it
with either paper.

## Page structure
- Volume index: `https://proceedings.mlr.press/v<N>/`. Its heading reads `Volume N: <proceedings title>`.
  Some volumes use `<h1>`, others `<h2>` (every ICML volume v28–v267 uses `<h2>`); take the first of
  either and strip the `Volume N: ` prefix. The PMLR index (`https://proceedings.mlr.press/`) lists every
  volume as `<li><a href="vN"><b>Volume N</b></a> <title></li>` (326 on 2026-09-27).
- Per-paper pages: `https://proceedings.mlr.press/v<N>/<key>.html` with a PDF beside it; the abstract is
  `<div id="abstract" class="abstract">`, the title `citation_title` (also repeated in twitter meta tags
  and the BibTeX/Endnote/APA boxes). The `<key>` is
  stable and gives the native id `pmlr-v<N>-<key>` (spec 01 §Record schema).
- Scholar and RIS records sometimes link the GitHub asset host instead
  (`raw.githubusercontent.com/mlresearch/v<N>/…`). Only the `mlresearch` organisation is PMLR.
- Strip HTML from abstracts, keep LaTeX verbatim (spec 03 decides tokenization), and collapse whitespace.

## Rules
1. **Only listed volumes are ingested.** PMLR hosts many unrelated venues (v318 is the Canadian
   Conference on AI). A volume missing from the table is out of scope. It never becomes ICML because its
   title looks similar.
2. **The year comes from the table**, not from the page footer, a PDF date or an arXiv date.
3. **Competition and workshop volumes never become `main`.** The track is a table column, never inferred.
4. Every record gets claims whose evidence is the volume index URL plus the paper URL, with the fetch time
   taken from the cache entry.
5. Every fetch goes through the disk cache (`.claude/skills/openreview-api/SKILL.md` has the retry rules,
   and the same HTTP client serves PMLR).
6. **The page must agree with the table.** The miner stops on a volume whose `Volume N: ` heading doesn't
   start with the row's `heading` (`heading_mismatch`): fix the table after checking the page, never the
   miner.

## The miner (as built, task-053)
`backend/src/openproceedings/ingest/sources/pmlr.py`, run by `op ingest pmlr --year <Y>` (the year's
ingested ICML volume from the table; `--dry-run`, `--offline`, `--refresh`, `--delay`), cache under
`<data-dir>/cache/pmlr/`. Per entry (`<div class="paper">`): title (`<p class="title">`), authors, the
`abs` page URL (the native key), the PDF (not `-supp.pdf`) and a v202/v235/v267-style OpenReview forum link
(`urls.forum`). Per paper page: `citation_title` (the abstract is taken only when it is the listed title,
tolerating a leading `$…$`), `citation_author`, `div#abstract`, `citation_pdf_url`. Claims (source `pmlr`):
venue, year and track with the table row as evidence (`volume table v28 (primary, verified 2026-09-27)`),
`accepted` with `listed on <index>`, the rest from the page they came from.

## Counting check
After a crawl, the paper count per volume must equal the number of paper entries on the volume index.
The listing report records both (`stated` = the table's verified count, `listed` = entries parsed,
`count_ok`) in the manifest's `sources.pmlr.listings`, so `coverage-auditor` can compare it with the
official accepted count; a mismatch logs `listing_count_mismatch`.
